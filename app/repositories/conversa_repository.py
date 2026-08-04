from datetime import datetime

from app.core.workspace_scope import apply_workspace_filter, stamp_workspace
from app.services.conversa_cliente_link import enriquecer_dados_conversa_com_cliente_id
from app.services.supabase_service import supabase


class ConversaRepository:

    def listar(self, workspace_id: str | None = None) -> list[dict]:
        query = (
            supabase
            .table("conversas")
            .select("*")
            .order("last_message_at", desc=True)
        )
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        return resposta.data or []

    def obter(self, conversa_id: str, workspace_id: str | None = None) -> dict | None:
        query = (
            supabase
            .table("conversas")
            .select("*")
            .eq("id", conversa_id)
            .limit(1)
        )
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        rows = resposta.data or []
        return rows[0] if rows else None

    def obter_por_thread(self, canal_id: str, external_thread_id: str) -> dict | None:
        resposta = (
            supabase
            .table("conversas")
            .select("*")
            .eq("canal_id", canal_id)
            .eq("external_thread_id", external_thread_id)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def criar(self, dados: dict, workspace_id: str | None = None) -> dict:
        payload = enriquecer_dados_conversa_com_cliente_id(dados)
        if workspace_id:
            payload = stamp_workspace(payload, workspace_id)
        resposta = supabase.table("conversas").insert(payload).execute()
        rows = resposta.data or []
        return rows[0] if rows else payload

    def atualizar(
        self,
        conversa_id: str,
        dados: dict,
        workspace_id: str | None = None,
    ) -> dict | None:
        existente = None
        if not dados.get("cliente_id"):
            existente = self.obter(conversa_id, workspace_id=workspace_id)
        payload = enriquecer_dados_conversa_com_cliente_id(dados, existente=existente)
        query = (
            supabase
            .table("conversas")
            .update({**payload, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", conversa_id)
        )
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        rows = resposta.data or []
        return rows[0] if rows else None

    def contar(self, workspace_id: str | None = None) -> int:
        query = supabase.table("conversas").select("*", count="exact")
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        return resposta.count or 0
