"""Aprendizado do agente: insights → extensões de instrução (gate humano).

Com AGENT_LEARNING_AUTO_PROMOTE/ACTIVATE=false no NSAgent, a promoção e a
ativação na persona ocorrem só via esta API (UI ChatBô).
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import HTTPException

from app.config.settings import NSAGENT_PERSONA_TENANT_ID
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

INSIGHT_STATUSES = frozenset(
    {"pending_review", "applied", "rejected", "superseded", "expired"}
)
EXTENSION_STATUSES = frozenset(
    {"pending_review", "active", "rejected", "superseded", "expired"}
)

# insight.category → extension.category (fallback)
_EXTENSION_CATEGORY = {
    "persona": "persona",
    "knowledge": "knowledge",
    "retrieval": "knowledge",
    "handoff": "policy",
    "greeting": "persona",
    "policy": "policy",
    "other": "persona",
}


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _hash_instruction(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _public_insight(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "tenantId": row.get("tenant_id"),
        "insightKey": row.get("insight_key"),
        "category": row.get("category"),
        "title": row.get("title"),
        "insightText": row.get("insight_text"),
        "evidenceCount": int(row.get("evidence_count") or 0),
        "confidence": float(row.get("confidence") or 0),
        "importance": float(row.get("importance") or 0),
        "status": row.get("status"),
        "appliedExtensionId": (
            int(row["applied_extension_id"])
            if row.get("applied_extension_id") is not None
            else None
        ),
        "metadata": row.get("metadata") or {},
        "firstSeenAt": row.get("first_seen_at"),
        "lastSeenAt": row.get("last_seen_at"),
        "reviewedAt": row.get("reviewed_at"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _public_extension(row: dict) -> dict:
    return {
        "id": int(row["id"]),
        "tenantId": row.get("tenant_id"),
        "workspaceId": row.get("workspace_id"),
        "extensionKey": row.get("extension_key"),
        "category": row.get("category"),
        "instructionText": row.get("instruction_text"),
        "source": row.get("source"),
        "status": row.get("status"),
        "importance": float(row["importance"]) if row.get("importance") is not None else None,
        "confidence": float(row["confidence"]) if row.get("confidence") is not None else None,
        "metadata": row.get("metadata") or {},
        "approvedBy": row.get("approved_by"),
        "approvedAt": row.get("approved_at"),
        "rejectedBy": row.get("rejected_by"),
        "rejectedAt": row.get("rejected_at"),
        "rejectionReason": row.get("rejection_reason"),
        "createdAt": row.get("created_at"),
        "updatedAt": row.get("updated_at"),
    }


def _public_review(row: dict) -> dict:
    failure_codes = row.get("failure_codes") or []
    if not isinstance(failure_codes, list):
        failure_codes = []
    return {
        "id": int(row["id"]),
        "responseId": int(row["response_id"]) if row.get("response_id") is not None else None,
        "channel": row.get("channel"),
        "outcome": row.get("outcome"),
        "failureCodes": [str(code) for code in failure_codes],
        "customerExcerpt": str(row.get("customer_text") or "")[:240],
        "agentExcerpt": str(row.get("agent_reply") or "")[:240],
        "createdAt": row.get("created_at"),
    }


def _public_case(row: dict) -> dict:
    failure_codes = row.get("failure_codes") or []
    if not isinstance(failure_codes, list):
        failure_codes = []
    return {
        "id": int(row["id"]),
        "caseKey": row.get("case_key"),
        "failureCodes": [str(code) for code in failure_codes],
        "customerExcerpt": str(row.get("customer_excerpt") or "")[:400],
        "badReply": str(row.get("bad_reply") or "")[:400],
        "correction": str(row.get("correction") or "")[:800],
        "status": row.get("status"),
        "importance": float(row.get("importance") or 0),
        "insightId": int(row["insight_id"]) if row.get("insight_id") is not None else None,
        "updatedAt": row.get("updated_at"),
    }


class AgentLearningService:
    def tenant_id(self) -> str:
        return (NSAGENT_PERSONA_TENANT_ID or "newstore").strip()

    def list_insights(
        self,
        *,
        workspace_id: str,
        status: str | None = "pending_review",
        limit: int = 50,
    ) -> dict:
        query = (
            supabase.table("ai_learning_insights")
            .select("*")
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .limit(min(max(limit, 1), 200))
        )
        if status:
            if status not in INSIGHT_STATUSES:
                raise HTTPException(status_code=400, detail="status de insight inválido")
            query = query.eq("status", status)
        rows = query.execute().data or []
        return {
            "items": [_public_insight(row) for row in rows],
            "total": len(rows),
            "tenantId": self.tenant_id(),
        }

    def list_extensions(
        self,
        *,
        workspace_id: str,
        status: str | None = "pending_review",
        limit: int = 50,
    ) -> dict:
        query = (
            supabase.table("ai_agent_instruction_extensions")
            .select("*")
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .limit(min(max(limit, 1), 200))
        )
        if status:
            if status not in EXTENSION_STATUSES:
                raise HTTPException(status_code=400, detail="status de extensão inválido")
            query = query.eq("status", status)
        rows = query.execute().data or []
        return {
            "items": [_public_extension(row) for row in rows],
            "total": len(rows),
            "tenantId": self.tenant_id(),
        }

    def list_reviews(self, *, workspace_id: str, limit: int = 30) -> list[dict]:
        rows = (
            supabase.table("ai_attendance_reviews")
            .select("id,response_id,channel,outcome,failure_codes,customer_text,agent_reply,created_at")
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .limit(min(max(limit, 1), 100))
            .execute()
            .data
            or []
        )
        return [_public_review(row) for row in rows]

    def list_cases(self, *, workspace_id: str, limit: int = 20) -> list[dict]:
        rows = (
            supabase.table("ai_learning_cases")
            .select("id,case_key,failure_codes,customer_excerpt,bad_reply,correction,status,importance,insight_id,updated_at")
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .eq("status", "active")
            .order("importance", desc=True)
            .limit(min(max(limit, 1), 100))
            .execute()
            .data
            or []
        )
        return [_public_case(row) for row in rows]

    def overview(self, *, workspace_id: str) -> dict:
        insights_pending = self.list_insights(workspace_id=workspace_id, status="pending_review", limit=100)
        extensions_pending = self.list_extensions(workspace_id=workspace_id, status="pending_review", limit=100)
        extensions_active = self.list_extensions(workspace_id=workspace_id, status="active", limit=50)
        reviews = self.list_reviews(workspace_id=workspace_id, limit=30)
        cases = self.list_cases(workspace_id=workspace_id, limit=20)
        cutoff = datetime.now(timezone.utc) - timedelta(hours=24)
        reviews_24h = [item for item in reviews if item.get("createdAt") and datetime.fromisoformat(str(item["createdAt"]).replace("Z", "+00:00")) >= cutoff]
        return {
            "tenantId": self.tenant_id(),
            "workspaceId": workspace_id,
            "pendingInsights": insights_pending["items"],
            "pendingExtensions": extensions_pending["items"],
            "activeExtensions": extensions_active["items"],
            "recentReviews": reviews,
            "activeCases": [item for item in cases if item.get("status") == "active"],
            "counts": {
                "pendingInsights": insights_pending["total"],
                "pendingExtensions": extensions_pending["total"],
                "activeExtensions": extensions_active["total"],
                "reviewsLast24h": len(reviews_24h),
                "failuresLast24h": sum(1 for item in reviews_24h if item.get("failureCodes")),
                "activeCases": sum(1 for item in cases if item.get("status") == "active"),
            },
        }

    def _get_insight(self, insight_id: int, *, workspace_id: str) -> dict:
        rows = (
            supabase.table("ai_learning_insights")
            .select("*")
            .eq("id", insight_id)
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Insight não encontrado")
        return rows[0]

    def _get_extension(self, extension_id: int, *, workspace_id: str) -> dict:
        rows = (
            supabase.table("ai_agent_instruction_extensions")
            .select("*")
            .eq("id", extension_id)
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        if not rows:
            raise HTTPException(status_code=404, detail="Extensão não encontrada")
        return rows[0]

    def _create_extension_from_insight(
        self,
        insight: dict,
        *,
        workspace_id: str | None,
    ) -> dict:
        insight_id = int(insight["id"])
        insight_category = str(insight.get("category") or "other")
        extension_category = _EXTENSION_CATEGORY.get(insight_category, "persona")
        # Se metadata já trouxe categoria de extensão, respeita
        meta = insight.get("metadata") if isinstance(insight.get("metadata"), dict) else {}
        if isinstance(meta.get("extension_category"), str) and meta["extension_category"]:
            extension_category = meta["extension_category"]

        extension_key = f"learning:{extension_category}:{insight_id}"
        instruction_text = str(insight.get("insight_text") or "").strip()
        if not instruction_text:
            raise HTTPException(status_code=400, detail="Insight sem texto para promover")

        # Reusa extensão já vinculada se ainda pendente
        existing_id = insight.get("applied_extension_id")
        if existing_id is not None:
            existing = self._get_extension(int(existing_id), workspace_id=workspace_id or "")
            if existing.get("status") in {"pending_review", "active"}:
                return existing

        now = _now_iso()
        payload: dict[str, Any] = {
            "tenant_id": self.tenant_id(),
            "scope": "tenant",
            "scope_key": None,
            "scope_key_norm": "",
            "extension_key": extension_key,
            "category": extension_category,
            "instruction_text": instruction_text,
            "instruction_hash": _hash_instruction(instruction_text),
            "source": "model_proposal",
            "status": "pending_review",
            "importance": float(insight.get("importance") or 0.5),
            "confidence": float(insight.get("confidence") or 0.5),
            "evidence_count": int(insight.get("evidence_count") or 1),
            "first_seen_at": now,
            "last_seen_at": now,
            "metadata": {
                "source": "attendance_learning",
                "insight_id": insight_id,
                "promoted_via": "chatbo_ui",
            },
            "created_at": now,
            "updated_at": now,
        }
        if workspace_id:
            payload["workspace_id"] = workspace_id

        created = (
            supabase.table("ai_agent_instruction_extensions").insert(payload).execute().data
            or []
        )
        if not created:
            raise HTTPException(status_code=502, detail="Falha ao criar extensão de instrução")
        extension = created[0]

        supabase.table("ai_learning_insights").update(
            {
                "applied_extension_id": extension["id"],
                "updated_at": now,
            }
        ).eq("id", insight_id).eq("tenant_id", self.tenant_id()).execute()

        return extension

    def promote_insight(
        self,
        insight_id: int,
        *,
        activate: bool = True,
        workspace_id: str | None = None,
        actor: str | None = None,
    ) -> dict:
        """Promove insight → extensão; com activate=True, aplica na persona (active)."""
        if not workspace_id:
            raise HTTPException(status_code=400, detail="Workspace obrigatorio")
        insight = self._get_insight(insight_id, workspace_id=workspace_id)
        if insight.get("status") == "rejected":
            raise HTTPException(status_code=409, detail="Insight já rejeitado")
        if insight.get("status") == "applied" and not activate:
            extension = None
            if insight.get("applied_extension_id") is not None:
                extension = self._get_extension(int(insight["applied_extension_id"]), workspace_id=workspace_id)
            return {
                "insight": _public_insight(insight),
                "extension": _public_extension(extension) if extension else None,
                "activated": extension.get("status") == "active" if extension else False,
            }

        extension = self._create_extension_from_insight(insight, workspace_id=workspace_id)
        activated = False
        if activate:
            extension = self._approve_extension_row(
                extension,
                actor=actor or "chatbo_ui",
            )
            activated = True
            now = _now_iso()
            supabase.table("ai_learning_insights").update(
                {
                    "status": "applied",
                    "applied_extension_id": extension["id"],
                    "reviewed_at": now,
                    "updated_at": now,
                }
            ).eq("id", insight_id).eq("tenant_id", self.tenant_id()).execute()
            insight = self._get_insight(insight_id, workspace_id=workspace_id)

        return {
            "insight": _public_insight(insight),
            "extension": _public_extension(extension),
            "activated": activated,
        }

    def _approve_extension_row(self, extension: dict, *, actor: str) -> dict:
        if extension.get("status") == "active":
            return extension
        if extension.get("status") not in {"pending_review", "rejected"}:
            raise HTTPException(
                status_code=409,
                detail=f"Extensão não pode ser aprovada (status={extension.get('status')})",
            )

        now = _now_iso()
        tenant_id = self.tenant_id()
        # Supersede outras active com a mesma chave
        supabase.table("ai_agent_instruction_extensions").update(
            {"status": "superseded", "updated_at": now}
        ).eq("tenant_id", tenant_id).eq("scope", extension.get("scope") or "tenant").eq(
            "scope_key_norm", extension.get("scope_key_norm") or ""
        ).eq("extension_key", extension["extension_key"]).eq("status", "active").neq(
            "id", extension["id"]
        ).execute()

        updated = (
            supabase.table("ai_agent_instruction_extensions")
            .update(
                {
                    "status": "active",
                    "approved_by": actor,
                    "approved_at": now,
                    "updated_at": now,
                    "rejected_by": None,
                    "rejected_at": None,
                    "rejection_reason": None,
                }
            )
            .eq("id", extension["id"])
            .eq("tenant_id", tenant_id)
            .execute()
            .data
            or []
        )
        if not updated:
            raise HTTPException(status_code=502, detail="Falha ao ativar extensão")
        return updated[0]

    def approve_extension(
        self,
        extension_id: int,
        *,
        workspace_id: str,
        actor: str | None = None,
    ) -> dict:
        extension = self._get_extension(extension_id, workspace_id=workspace_id)
        approved = self._approve_extension_row(extension, actor=actor or "chatbo_ui")

        # Marca insight vinculado como applied
        meta = approved.get("metadata") if isinstance(approved.get("metadata"), dict) else {}
        insight_id = meta.get("insight_id")
        now = _now_iso()
        if insight_id is not None:
            supabase.table("ai_learning_insights").update(
                {
                    "status": "applied",
                    "applied_extension_id": approved["id"],
                    "reviewed_at": now,
                    "updated_at": now,
                }
            ).eq("id", int(insight_id)).eq("tenant_id", self.tenant_id()).execute()
        else:
            supabase.table("ai_learning_insights").update(
                {
                    "status": "applied",
                    "reviewed_at": now,
                    "updated_at": now,
                }
            ).eq("applied_extension_id", approved["id"]).eq(
                "tenant_id", self.tenant_id()
            ).execute()

        return {"extension": _public_extension(approved), "activated": True}

    def reject_insight(
        self,
        insight_id: int,
        *,
        workspace_id: str,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict:
        insight = self._get_insight(insight_id, workspace_id=workspace_id)
        if insight.get("status") == "applied":
            raise HTTPException(status_code=409, detail="Insight já aplicado na persona")

        now = _now_iso()
        meta = insight.get("metadata") if isinstance(insight.get("metadata"), dict) else {}
        meta = {
            **meta,
            "rejected_by": actor or "chatbo_ui",
            "rejection_reason": (reason or "").strip() or None,
        }
        updated = (
            supabase.table("ai_learning_insights")
            .update(
                {
                    "status": "rejected",
                    "reviewed_at": now,
                    "updated_at": now,
                    "metadata": meta,
                }
            )
            .eq("id", insight_id)
            .eq("tenant_id", self.tenant_id())
            .execute()
            .data
            or []
        )
        if not updated:
            raise HTTPException(status_code=502, detail="Falha ao rejeitar insight")

        # Rejeita extensão pendente vinculada
        if insight.get("applied_extension_id") is not None:
            try:
                self.reject_extension(
                    int(insight["applied_extension_id"]),
                    workspace_id=workspace_id,
                    reason=reason,
                    actor=actor,
                )
            except HTTPException:
                pass

        return {"insight": _public_insight(updated[0])}

    def reject_extension(
        self,
        extension_id: int,
        *,
        workspace_id: str,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict:
        extension = self._get_extension(extension_id, workspace_id=workspace_id)
        if extension.get("status") == "active":
            raise HTTPException(
                status_code=409,
                detail="Extensão ativa: rejeite via nova promoção ou supersede",
            )
        if extension.get("status") == "rejected":
            return {"extension": _public_extension(extension)}

        now = _now_iso()
        updated = (
            supabase.table("ai_agent_instruction_extensions")
            .update(
                {
                    "status": "rejected",
                    "rejected_by": actor or "chatbo_ui",
                    "rejected_at": now,
                    "rejection_reason": (reason or "").strip() or None,
                    "updated_at": now,
                }
            )
            .eq("id", extension_id)
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .execute()
            .data
            or []
        )
        if not updated:
            raise HTTPException(status_code=502, detail="Falha ao rejeitar extensão")
        return {"extension": _public_extension(updated[0])}

    def retire_extension(
        self,
        extension_id: int,
        *,
        workspace_id: str,
        reason: str | None = None,
        actor: str | None = None,
    ) -> dict:
        extension = self._get_extension(extension_id, workspace_id=workspace_id)
        if extension.get("status") != "active":
            raise HTTPException(status_code=409, detail="Somente uma extensao ativa pode ser desativada")
        now = _now_iso()
        metadata = extension.get("metadata") if isinstance(extension.get("metadata"), dict) else {}
        updated = (
            supabase.table("ai_agent_instruction_extensions")
            .update({
                "status": "superseded",
                "rejection_reason": (reason or "").strip() or "Desativada pelo operador",
                "updated_at": now,
                "metadata": {**metadata, "retired_by": actor or "chatbo_ui", "retired_at": now},
            })
            .eq("id", extension_id)
            .eq("tenant_id", self.tenant_id())
            .eq("workspace_id", workspace_id)
            .execute()
            .data
            or []
        )
        if not updated:
            raise HTTPException(status_code=502, detail="Falha ao desativar extensao")
        return {"extension": _public_extension(updated[0])}


agent_learning_service = AgentLearningService()
