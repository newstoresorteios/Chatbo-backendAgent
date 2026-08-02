from datetime import datetime

from app.services.supabase_service import supabase


class UsuarioRepository:

    def buscar_por_email(self, email: str) -> dict | None:
        resposta = (
            supabase
            .table("usuarios")
            .select("*")
            .eq("email", email.strip().lower())
            .limit(1)
            .execute()
        )

        rows = resposta.data or []
        return rows[0] if rows else None

    def buscar_por_id(self, usuario_id: str) -> dict | None:
        resposta = (
            supabase
            .table("usuarios")
            .select("*")
            .eq("id", usuario_id)
            .limit(1)
            .execute()
        )

        rows = resposta.data or []
        return rows[0] if rows else None

    def buscar_por_reset_token(self, token: str) -> dict | None:
        resposta = (
            supabase
            .table("usuarios")
            .select("*")
            .eq("reset_token", token)
            .limit(1)
            .execute()
        )

        rows = resposta.data or []
        return rows[0] if rows else None

    def criar(self, dados: dict) -> dict:
        resposta = (
            supabase
            .table("usuarios")
            .insert(dados)
            .execute()
        )

        rows = resposta.data or []
        return rows[0] if rows else dados

    def atualizar(self, usuario_id: str, dados: dict) -> dict | None:
        resposta = (
            supabase
            .table("usuarios")
            .update({**dados, "updated_at": datetime.utcnow().isoformat()})
            .eq("id", usuario_id)
            .execute()
        )

        rows = resposta.data or []
        return rows[0] if rows else None

    def excluir(self, usuario_id: str) -> None:
        (
            supabase
            .table("usuarios")
            .delete()
            .eq("id", usuario_id)
            .execute()
        )

    def listar_emails(self) -> list[str]:
        resposta = (
            supabase
            .table("usuarios")
            .select("email")
            .execute()
        )

        return [row["email"] for row in (resposta.data or [])]

    def listar(self) -> list[dict]:
        resposta = (
            supabase
            .table("usuarios")
            .select("id,email,nome,perfil,ativo,empresa,created_at,updated_at")
            .order("nome")
            .execute()
        )
        return resposta.data or []

    def listar_por_ids(self, usuario_ids: list[str]) -> list[dict]:
        if not usuario_ids:
            return []
        resposta = (
            supabase
            .table("usuarios")
            .select("id,email,nome,perfil,ativo,empresa,created_at,updated_at")
            .in_("id", usuario_ids)
            .order("nome")
            .execute()
        )
        return resposta.data or []
