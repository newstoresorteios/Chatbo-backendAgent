from datetime import datetime

from app.services.supabase_service import supabase


class PersonaRepository:
    def listar_por_workspace(self, workspace_id: str) -> list[dict]:
        resposta = (
            supabase
            .table("agent_personas")
            .select("*")
            .eq("workspace_id", workspace_id)
            .order("updated_at", desc=True)
            .execute()
        )
        return resposta.data or []

    def buscar_por_id_workspace(self, persona_id: str, workspace_id: str) -> dict | None:
        resposta = (
            supabase
            .table("agent_personas")
            .select("*")
            .eq("id", persona_id)
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def buscar_ativa(self, workspace_id: str) -> dict | None:
        resposta = (
            supabase
            .table("agent_personas")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("status", "active")
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def criar(self, payload: dict) -> dict:
        resposta = supabase.table("agent_personas").insert(payload).execute()
        rows = resposta.data or []
        return rows[0] if rows else payload

    def atualizar(self, persona_id: str, workspace_id: str, payload: dict) -> dict:
        resposta = (
            supabase
            .table("agent_personas")
            .update({**payload, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", persona_id)
            .eq("workspace_id", workspace_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else {"id": persona_id, "workspace_id": workspace_id, **payload}

    def criar_versao(self, payload: dict) -> dict:
        resposta = supabase.table("agent_persona_versions").insert(payload).execute()
        rows = resposta.data or []
        return rows[0] if rows else payload

    def listar_versoes(self, persona_id: str, workspace_id: str) -> list[dict]:
        resposta = (
            supabase
            .table("agent_persona_versions")
            .select("*")
            .eq("persona_id", persona_id)
            .eq("workspace_id", workspace_id)
            .order("version", desc=True)
            .execute()
        )
        return resposta.data or []

    def buscar_versao(self, persona_id: str, workspace_id: str, version: int) -> dict | None:
        resposta = (
            supabase
            .table("agent_persona_versions")
            .select("*")
            .eq("persona_id", persona_id)
            .eq("workspace_id", workspace_id)
            .eq("version", version)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None
