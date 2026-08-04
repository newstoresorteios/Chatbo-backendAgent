from datetime import datetime

from app.services.supabase_service import supabase


class AgentRegistryRepository:
    def listar_tipos(self) -> list[dict]:
        resposta = (
            supabase.table("agent_runtime_types")
            .select("*")
            .order("code")
            .execute()
        )
        return resposta.data or []

    def obter_tipo(self, code: str) -> dict | None:
        resposta = (
            supabase.table("agent_runtime_types")
            .select("*")
            .eq("code", code)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def obter_por_workspace(self, workspace_id: str) -> dict | None:
        resposta = (
            supabase.table("workspace_agents")
            .select("*, agent_runtime_types(code, name, base_runtime, description)")
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def criar(self, payload: dict) -> dict:
        resposta = supabase.table("workspace_agents").insert(payload).execute()
        rows = resposta.data or []
        return rows[0] if rows else payload

    def atualizar(self, workspace_id: str, payload: dict) -> dict | None:
        resposta = (
            supabase.table("workspace_agents")
            .update({**payload, "updated_at": datetime.utcnow().isoformat()})
            .eq("workspace_id", workspace_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def upsert(self, workspace_id: str, payload: dict) -> dict:
        existente = self.obter_por_workspace(workspace_id)
        if existente:
            updated = self.atualizar(workspace_id, payload)
            return updated or existente
        return self.criar({"workspace_id": workspace_id, **payload})
