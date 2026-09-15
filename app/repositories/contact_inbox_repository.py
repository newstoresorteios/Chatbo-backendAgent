"""Contact read model. All lookups require a server-resolved workspace."""
from app.services.supabase_service import supabase
from datetime import datetime
from uuid import UUID


class ContactInboxRepository:
    def listar(self, workspace_id: str, *, limit: int, before: str | None = None) -> list[dict]:
        query = (supabase.table("conversation_contact_inbox").select("*")
                 .eq("workspace_id", workspace_id).order("last_message_at", desc=True).order("id"))
        if before:
            query = query.lt("last_message_at", before)
        return query.limit(limit).execute().data or []

    def obter(self, conversation_id: str, workspace_id: str) -> dict | None:
        rows = (supabase.table("conversation_contact_inbox").select("*")
                .eq("workspace_id", workspace_id).contains("session_ids", [conversation_id])
                .limit(1).execute().data or [])
        return rows[0] if rows else None

    def sessoes(self, group: dict, workspace_id: str) -> list[dict]:
        rows = []
        ids = group["session_ids"]
        for offset in range(0, len(ids), 100):
            rows.extend(supabase.table("conversas").select("*").eq("workspace_id", workspace_id)
                        .in_("id", ids[offset:offset + 100]).execute().data or [])
        return rows

    def atualizar_abertas(self, group: dict, workspace_id: str, patch: dict) -> list[dict]:
        return (supabase.table("conversas").update(patch).eq("workspace_id", workspace_id)
                .in_("id", group["session_ids"]).neq("status", "closed").execute().data or [])

    def mensagens(self, group: dict, workspace_id: str, *, limit: int,
                  before: str | None = None, before_id: str | None = None, after: str | None = None) -> list[dict]:
        # Chunk IDs, then take a global page; no session's older history is omitted.
        rows = []
        ids = group["session_ids"]
        for offset in range(0, len(ids), 100):
            query = (supabase.table("mensagens").select("*").or_(f"workspace_id.eq.{workspace_id},workspace_id.is.null")
                     .in_("conversa_id", ids[offset:offset + 100]))
            if before:
                if before_id:
                    timestamp = datetime.fromisoformat(before.replace('Z', '+00:00')).isoformat()
                    cursor_id = str(UUID(before_id))
                    query = query.or_(f"created_at.lt.{timestamp},and(created_at.eq.{timestamp},id.lt.{cursor_id})")
                else:
                    query = query.lt("created_at", before)
            if after:
                query = query.gt("created_at", after)
            rows.extend(query.order("created_at", desc=True).order("id", desc=True)
                        .limit(limit).execute().data or [])
        return sorted(rows, key=lambda r: (r["created_at"], str(r["id"])))[-limit:]
