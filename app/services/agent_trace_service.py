from typing import Any

from fastapi import HTTPException

from app.repositories.agent_trace_repository import AgentTraceRepository
from app.services.workspace_service import workspace_service


TRACE_VIEW_ROLES = {"owner", "admin", "supervisor"}


def _dict(value: Any) -> dict:
    return value if isinstance(value, dict) else {}


class AgentTraceService:
    def __init__(self):
        self.repo = AgentTraceRepository()

    def _workspace_id(self, usuario: dict) -> str:
        context = workspace_service.get_current_workspace_context(usuario)
        if context.get("workspaceRole") not in TRACE_VIEW_ROLES:
            raise HTTPException(status_code=403, detail="Sem permissão para visualizar execuções do agente")
        return str(context["workspaceId"])

    def _schema_unavailable(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "workspace_id" in text or "ai_agent_responses" in text

    def _parts(self, row: dict) -> tuple[dict, dict, dict]:
        provider = _dict(row.get("provider_response"))
        metadata = _dict(provider.get("_agent_metadata"))
        runtime = _dict(metadata.get("turn_runtime"))
        return metadata, runtime, _dict(metadata.get("persona_runtime"))

    def _outcome(self, row: dict, runtime: dict) -> str:
        if not row.get("provider_send_ok"):
            return "failed"
        if row.get("handoff_required"):
            return "handoff"
        if runtime.get("fallback_reasons"):
            return "fallback"
        return "delivered"

    def _summary(self, row: dict) -> dict:
        metadata, runtime, persona = self._parts(row)
        inbound = _dict(runtime.get("inbound"))
        outbound = _dict(runtime.get("outbound"))
        return {
            "id": int(row["id"]),
            "traceId": runtime.get("trace_id") or f"response-{row['id']}",
            "inboundId": row.get("inbound_id"),
            "channel": row.get("channel") or runtime.get("channel") or "unknown",
            "outcome": self._outcome(row, runtime),
            "intent": row.get("intent"),
            "executionPath": runtime.get("execution_path") or "unknown",
            "durationMs": float(runtime.get("processing_total_ms") or 0),
            "openAiCalls": int(runtime.get("openai_call_count") or 0),
            "trayCalls": int(runtime.get("tray_call_count") or 0),
            "databaseCalls": int(runtime.get("database_call_count") or 0),
            "inputTokens": int(runtime.get("openai_input_tokens") or 0),
            "outputTokens": int(runtime.get("openai_output_tokens") or 0),
            "inputPreview": inbound.get("text_preview"),
            "outputPreview": outbound.get("reply_preview"),
            "fallbackReasons": list(runtime.get("fallback_reasons") or []),
            "safetyReason": row.get("safety_reason"),
            "personaVersionId": persona.get("persona_version_id"),
            "configurationKeys": list(persona.get("runtime_configuration_keys") or []),
            "createdAt": row.get("created_at"),
            "responseSource": metadata.get("response_source"),
        }

    def listar(
        self,
        usuario: dict,
        *,
        limit: int,
        before: str | None,
        channel: str | None,
        outcome: str | None,
    ) -> dict:
        workspace_id = self._workspace_id(usuario)
        delivered = None
        handoff = None
        if outcome == "failed":
            delivered = False
        elif outcome == "handoff":
            handoff = True
        elif outcome in {"delivered", "fallback"}:
            delivered = True

        scan_limit = min(limit * 3, 300) if outcome in {"delivered", "fallback"} else limit
        try:
            rows = self.repo.listar(
                workspace_id,
                limit=scan_limit,
                before=before,
                channel=channel,
                delivered=delivered,
                handoff=handoff,
            )
        except Exception as exc:
            if self._schema_unavailable(exc):
                raise HTTPException(status_code=503, detail="Execute supabase/025_agent_turn_traces.sql no Supabase.") from exc
            raise
        has_more_rows = len(rows) > scan_limit
        scanned = rows[:scan_limit]
        items = [self._summary(row) for row in scanned]
        if outcome in {"delivered", "fallback"}:
            items = [item for item in items if item["outcome"] == outcome]
        has_next = has_more_rows or len(items) > limit
        items = items[:limit]
        return {
            "items": items,
            "hasNext": has_next,
            "nextCursor": scanned[-1].get("created_at") if has_next and scanned else None,
        }

    def obter(self, usuario: dict, response_id: int) -> dict:
        workspace_id = self._workspace_id(usuario)
        try:
            row = self.repo.obter(response_id, workspace_id)
        except Exception as exc:
            if self._schema_unavailable(exc):
                raise HTTPException(status_code=503, detail="Execute supabase/025_agent_turn_traces.sql no Supabase.") from exc
            raise
        if not row:
            raise HTTPException(status_code=404, detail="Execução não encontrada")
        metadata, runtime, persona = self._parts(row)
        return {
            **self._summary(row),
            "stages": _dict(runtime.get("stage_durations_ms")),
            "llmCalls": list(runtime.get("openai_calls") or []),
            "llmCallsByType": _dict(runtime.get("llm_calls_by_type")),
            "trayTools": list(runtime.get("tray_tools") or []),
            "integrationFailures": _dict(runtime.get("integration_failures")),
            "inbound": _dict(runtime.get("inbound")),
            "context": _dict(runtime.get("context")),
            "outbound": _dict(runtime.get("outbound")),
            "qualityJudge": _dict(metadata.get("quality_judge")),
            "factualValidation": _dict(metadata.get("factual_validation")),
            "personaRuntime": persona,
        }


agent_trace_service = AgentTraceService()
