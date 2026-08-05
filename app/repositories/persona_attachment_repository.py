from datetime import datetime

from app.services.supabase_service import supabase


class PersonaAttachmentRepository:
    def listar(self, persona_id: str, workspace_id: str) -> list[dict]:
        resposta = (
            supabase.table("agent_persona_attachments")
            .select("*")
            .eq("persona_id", persona_id)
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .execute()
        )
        return resposta.data or []

    def listar_processados(self, persona_id: str, workspace_id: str) -> list[dict]:
        resposta = (
            supabase.table("agent_persona_attachments")
            .select("id,filename,extracted_text,status,byte_size")
            .eq("persona_id", persona_id)
            .eq("workspace_id", workspace_id)
            .eq("status", "processed")
            .order("created_at", desc=False)
            .execute()
        )
        return resposta.data or []

    def buscar(self, attachment_id: str, persona_id: str, workspace_id: str) -> dict | None:
        resposta = (
            supabase.table("agent_persona_attachments")
            .select("*")
            .eq("id", attachment_id)
            .eq("persona_id", persona_id)
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def criar(self, payload: dict) -> dict:
        resposta = supabase.table("agent_persona_attachments").insert(payload).execute()
        rows = resposta.data or []
        return rows[0] if rows else payload

    def atualizar(self, attachment_id: str, workspace_id: str, payload: dict) -> dict:
        resposta = (
            supabase.table("agent_persona_attachments")
            .update({**payload, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", attachment_id)
            .eq("workspace_id", workspace_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else {"id": attachment_id, **payload}

    def remover(self, attachment_id: str, workspace_id: str) -> None:
        (
            supabase.table("agent_persona_attachments")
            .delete()
            .eq("id", attachment_id)
            .eq("workspace_id", workspace_id)
            .execute()
        )

    def contar(self, persona_id: str, workspace_id: str) -> int:
        resposta = (
            supabase.table("agent_persona_attachments")
            .select("id", count="exact")
            .eq("persona_id", persona_id)
            .eq("workspace_id", workspace_id)
            .execute()
        )
        if getattr(resposta, "count", None) is not None:
            return int(resposta.count or 0)
        return len(resposta.data or [])
