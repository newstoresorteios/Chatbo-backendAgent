from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.agent_conversation_ingest import AgentConversationTurn
from app.services.ai_conversas_bridge import ai_conversas_bridge
from app.services.supabase_service import supabase


class AgentConversationIngestRepository:
    def find_inbound(self, provider: str, message_id: str) -> dict | None:
        rows = (
            supabase.table("ai_inbound_messages")
            .select("*")
            .eq("provider", provider)
            .eq("message_id", message_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None

    def insert_inbound(self, payload: dict[str, Any]) -> dict:
        rows = supabase.table("ai_inbound_messages").insert(payload).execute().data or []
        if not rows:
            raise RuntimeError("agent_inbound_insert_failed")
        return rows[0]

    def find_response(self, workspace_id: str, source_event_key: str) -> dict | None:
        rows = (
            supabase.table("ai_agent_responses")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("source_event_key", source_event_key)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None

    def insert_response(self, payload: dict[str, Any]) -> dict:
        rows = supabase.table("ai_agent_responses").insert(payload).execute().data or []
        if not rows:
            raise RuntimeError("agent_response_insert_failed")
        return rows[0]


class AgentConversationIngestService:
    def __init__(
        self,
        repository: AgentConversationIngestRepository | None = None,
        workspace_repository: WorkspaceRepository | None = None,
        bridge: Any | None = None,
    ) -> None:
        self.repository = repository or AgentConversationIngestRepository()
        self.workspace_repository = workspace_repository or WorkspaceRepository()
        self.bridge = bridge or ai_conversas_bridge

    def ingest_turn(self, workspace_id: str, turn: AgentConversationTurn) -> dict[str, Any]:
        workspace = self.workspace_repository.buscar_workspace(workspace_id)
        if not workspace or workspace.get("status") not in {None, "active", "trial"}:
            raise HTTPException(status_code=404, detail="Workspace não encontrado ou inativo.")

        inbound_data = turn.inbound.model_dump(by_alias=False, exclude_none=True)
        created_at = inbound_data.pop("created_at", None)
        inbound_payload = {
            **inbound_data,
            "workspace_id": workspace_id,
            "raw": {},
        }
        if created_at is not None:
            inbound_payload["created_at"] = created_at.isoformat()

        inbound = self.repository.find_inbound(turn.inbound.provider, turn.inbound.message_id)
        inbound_created = inbound is None
        if inbound is not None and str(inbound.get("workspace_id") or "") != workspace_id:
            raise HTTPException(status_code=409, detail="Mensagem já pertence a outro workspace.")
        if inbound is None:
            try:
                inbound = self.repository.insert_inbound(inbound_payload)
            except Exception:
                # A retry or a concurrent webhook may have won the unique-key race.
                inbound = self.repository.find_inbound(
                    turn.inbound.provider, turn.inbound.message_id
                )
                if inbound is None:
                    raise
                inbound_created = False
                if str(inbound.get("workspace_id") or "") != workspace_id:
                    raise HTTPException(
                        status_code=409,
                        detail="Mensagem já pertence a outro workspace.",
                    )
        self.bridge.sync_event("ai_inbound_messages", inbound)

        response = None
        response_created = False
        if turn.response is not None:
            inbound_id = inbound.get("id")
            if inbound_id is None:
                raise RuntimeError("agent_inbound_id_missing")
            source_event_key = f"{turn.inbound.provider}:{turn.inbound.message_id}:agent"
            response = self.repository.find_response(workspace_id, source_event_key)
            response_created = response is None
            if response is None:
                response_data = turn.response.model_dump(by_alias=False, exclude_none=True)
                response_created_at = response_data.pop("created_at", None)
                response_payload = {
                    **response_data,
                    "workspace_id": workspace_id,
                    "inbound_id": inbound_id,
                    "source_event_key": source_event_key,
                    "channel": turn.inbound.channel,
                    "sender_key": turn.inbound.sender_key,
                    "sender_phone": turn.inbound.sender_phone,
                }
                if response_created_at is not None:
                    response_payload["created_at"] = response_created_at.isoformat()
                try:
                    response = self.repository.insert_response(response_payload)
                except Exception:
                    # The partial unique index makes response retries idempotent.
                    response = self.repository.find_response(workspace_id, source_event_key)
                    if response is None:
                        raise
                    response_created = False
            self.bridge.sync_event("ai_agent_responses", response)

        return {
            "ok": True,
            "workspaceId": workspace_id,
            "inboundId": inbound.get("id"),
            "responseId": response.get("id") if response else None,
            "inboundCreated": inbound_created,
            "responseCreated": response_created,
        }


agent_conversation_ingest_service = AgentConversationIngestService()
