from app.services.supabase_service import supabase
from datetime import datetime
from fastapi import HTTPException


TRACE_COLUMNS = (
    "id,inbound_id,workspace_id,channel,intent,handoff_required,safety_reason,"
    "provider_send_ok,provider_response,created_at"
)


class AgentTraceRepository:
    def listar(
        self,
        workspace_id: str,
        *,
        limit: int,
        before: str | None = None,
        channel: str | None = None,
        delivered: bool | None = None,
        handoff: bool | None = None,
    ) -> list[dict]:
        query = (
            supabase.table("ai_agent_trace_summaries")
            .select(TRACE_COLUMNS)
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .order("id", desc=True)
            .limit(limit + 1)
        )
        if before:
            try:
                timestamp, separator, row_id = before.partition("|")
                timestamp = datetime.fromisoformat(timestamp.replace("Z", "+00:00")).isoformat()
                if separator:
                    row_id = int(row_id)
                    query = query.or_(f"created_at.lt.{timestamp},and(created_at.eq.{timestamp},id.lt.{row_id})")
                else:
                    query = query.lt("created_at", timestamp)
            except ValueError as exc:
                raise HTTPException(status_code=422, detail="Cursor de paginação inválido") from exc
        if channel:
            query = query.eq("channel", channel)
        if delivered is not None:
            query = query.eq("provider_send_ok", delivered)
        if handoff is not None:
            query = query.eq("handoff_required", handoff)
        return query.execute().data or []

    def obter(self, response_id: int, workspace_id: str) -> dict | None:
        rows = (
            supabase.table("ai_agent_responses")
            .select(TRACE_COLUMNS)
            .eq("id", response_id)
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
