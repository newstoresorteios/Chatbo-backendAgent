from datetime import datetime

from app.services.conversa_cliente_link import enriquecer_dados_conversa_com_cliente_id
from app.services.supabase_service import supabase


class ConversaRepository:

    def listar(self) -> list[dict]:
        resposta = (
            supabase
            .table("conversas")
            .select("*")
            .order("last_message_at", desc=True)
            .execute()
        )
        return resposta.data or []

    def obter(self, conversa_id: str) -> dict | None:
        resposta = (
            supabase
            .table("conversas")
            .select("*")
            .eq("id", conversa_id)
            .limit(1)
            .execute()
        )
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

    def criar(self, dados: dict) -> dict:
        payload = enriquecer_dados_conversa_com_cliente_id(dados)
        resposta = supabase.table("conversas").insert(payload).execute()
        rows = resposta.data or []
        return rows[0] if rows else payload

    def atualizar(self, conversa_id: str, dados: dict) -> dict | None:
        existente = None
        if not dados.get("cliente_id"):
            existente = self.obter(conversa_id)
        payload = enriquecer_dados_conversa_com_cliente_id(dados, existente=existente)
        resposta = (
            supabase
            .table("conversas")
            .update({**payload, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", conversa_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def contar(self) -> int:
        resposta = supabase.table("conversas").select("*", count="exact").execute()
        return resposta.count or 0
