from datetime import datetime

from app.core.workspace_scope import apply_workspace_filter, stamp_workspace
from app.services.conversa_cliente_link import enriquecer_dados_conversa_com_cliente_id
from app.services.supabase_service import supabase


class ConversaRepository:

    def listar(
        self,
        workspace_id: str | None = None,
        *,
        max_rows: int = 2000,
        before: str | None = None,
    ) -> list[dict]:
        rows: list[dict] = []
        offset = 0
        while offset < max_rows:
            page_size = min(500, max_rows - offset)
            query = (
                supabase
                .table("conversas")
                .select("*")
                .is_("merged_into", "null")
                .order("last_message_at", desc=True)
                .range(offset, offset + page_size - 1)
            )
            if workspace_id:
                query = apply_workspace_filter(query, workspace_id)
            if before:
                query = query.lt("last_message_at", before)
            resposta = query.execute()
            batch = resposta.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return rows

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
        if rows and rows[0].get("merged_into"):
            return self.obter(str(rows[0]["merged_into"]), workspace_id=workspace_id or rows[0].get("workspace_id"))
        return rows[0] if rows else None

    def obter_por_thread(self, canal_id: str, external_thread_id: str) -> dict | None:
        resposta = (
            supabase
            .table("conversas")
            .select("*")
            .eq("canal_id", canal_id)
            .eq("external_thread_id", external_thread_id)
            .is_("merged_into", "null")
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def obter_por_contato(
        self,
        identity: str,
        workspace_id: str | None = None,
        channel: str | None = None,
    ) -> dict | None:
        """Busca conversa por telefone / thread externa no workspace."""
        if not identity:
            return None
        for column in ("external_thread_id", "contact_phone"):
            query = (
                supabase
                .table("conversas")
                .select("*")
                .eq(column, identity)
                .is_("merged_into", "null")
                .order("last_message_at", desc=True)
                .limit(1)
            )
            if workspace_id:
                query = apply_workspace_filter(query, workspace_id)
            if channel:
                query = query.eq("channel", channel)
            rows = (query.execute().data) or []
            if rows:
                return rows[0]
        return None

    def listar_legado_sem_workspace(
        self,
        *,
        max_rows: int = 2000,
        before: str | None = None,
    ) -> list[dict]:
        """Conversas antigas sem workspace_id (fallback do inbox)."""
        rows: list[dict] = []
        offset = 0
        while offset < max_rows:
            page_size = min(500, max_rows - offset)
            query = (
                supabase
                .table("conversas")
                .select("*")
                .is_("workspace_id", "null")
                .order("last_message_at", desc=True)
                .range(offset, offset + page_size - 1)
            )
            if before:
                query = query.lt("last_message_at", before)
            resposta = query.execute()
            batch = resposta.data or []
            rows.extend(batch)
            if len(batch) < page_size:
                break
            offset += page_size
        return rows

    def criar(self, dados: dict, workspace_id: str | None = None) -> dict:
        payload = enriquecer_dados_conversa_com_cliente_id(dados)
        if workspace_id:
            payload = stamp_workspace(payload, workspace_id)
        try:
            resposta = supabase.table("conversas").insert(payload).execute()
        except Exception as exc:
            if "idx_conversas_workspace_session_unique" not in str(exc):
                raise
            query = (supabase.table("conversas").select("*")
                .eq("workspace_id", payload["workspace_id"])
                .eq("channel", payload["channel"])
                .eq("external_thread_id", payload["external_thread_id"])
                .is_("merged_into", "null"))
            query = query.eq("canal_id", payload["canal_id"]) if payload.get("canal_id") else query.is_("canal_id", "null")
            rows = query.limit(1).execute().data or []
            if not rows:
                raise
            return rows[0]
        rows = resposta.data or []
        return rows[0] if rows else payload

    def atualizar(
        self,
        conversa_id: str,
        dados: dict,
        workspace_id: str | None = None,
    ) -> dict | None:
        existente = self.obter(conversa_id, workspace_id=workspace_id)
        if existente:
            conversa_id = str(existente["id"])
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

    def marcar_lida(
        self,
        conversa_id: str,
        user_id: str,
        unread_count: int,
        workspace_id: str,
    ) -> dict | None:
        """Zera apenas a contagem observada; uma mensagem nova impede o update."""
        query = (
            supabase.table("conversas")
            .update({"unread_count": 0, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", conversa_id)
            .eq("assigned_to", user_id)
            .eq("unread_count", unread_count)
        )
        resposta = apply_workspace_filter(query, workspace_id).execute()
        rows = resposta.data or []
        return rows[0] if rows else None

    def contar(self, workspace_id: str | None = None) -> int:
        query = supabase.table("conversas").select("*", count="exact").is_("merged_into", "null")
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        return resposta.count or 0
