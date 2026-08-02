from app.services.supabase_service import supabase


class MensagemRepository:

    def listar_por_conversa(self, conversa_id: str) -> list[dict]:
        resposta = (
            supabase
            .table("mensagens")
            .select("*")
            .eq("conversa_id", conversa_id)
            .order("created_at", desc=False)
            .execute()
        )
        return resposta.data or []

    def criar(self, dados: dict) -> dict:
        resposta = supabase.table("mensagens").insert(dados).execute()
        rows = resposta.data or []
        return rows[0] if rows else dados

    def existe_external_id(self, external_id: str) -> bool:
        if not external_id:
            return False
        resposta = (
            supabase
            .table("mensagens")
            .select("id")
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        return bool(resposta.data)

    def atualizar(self, mensagem_id: str, dados: dict) -> dict | None:
        resposta = (
            supabase
            .table("mensagens")
            .update(dados)
            .eq("id", mensagem_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def atualizar_por_external_id(self, external_id: str, dados: dict) -> dict | None:
        resposta = (
            supabase
            .table("mensagens")
            .update(dados)
            .eq("external_id", external_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None
