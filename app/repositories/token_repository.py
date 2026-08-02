import hashlib
from datetime import datetime

from app.services.supabase_service import supabase


def _hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


class TokenRepository:

    def revogar_jti(self, jti: str, usuario_id: str, expira_em: datetime) -> None:
        supabase.table("token_revogados").upsert({
            "jti": jti,
            "usuario_id": usuario_id,
            "expira_em": expira_em.isoformat(),
            "revogado_em": datetime.utcnow().isoformat(),
        }).execute()

    def jti_revogado(self, jti: str) -> bool:
        resposta = (
            supabase
            .table("token_revogados")
            .select("jti")
            .eq("jti", jti)
            .limit(1)
            .execute()
        )
        return bool(resposta.data)

    def limpar_revogados_expirados(self) -> None:
        try:
            supabase.table("token_revogados").delete().lt(
                "expira_em", datetime.utcnow().isoformat(),
            ).execute()
        except Exception:
            pass

    def salvar_refresh(self, usuario_id: str, token_plain: str, expira_em: datetime) -> None:
        supabase.table("refresh_tokens").insert({
            "usuario_id": usuario_id,
            "token_hash": _hash_token(token_plain),
            "expira_em": expira_em.isoformat(),
        }).execute()

    def buscar_refresh(self, token_plain: str) -> dict | None:
        resposta = (
            supabase
            .table("refresh_tokens")
            .select("*")
            .eq("token_hash", _hash_token(token_plain))
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def revogar_refresh(self, token_plain: str) -> None:
        supabase.table("refresh_tokens").delete().eq(
            "token_hash", _hash_token(token_plain),
        ).execute()

    def revogar_todos_refresh_usuario(self, usuario_id: str) -> None:
        supabase.table("refresh_tokens").delete().eq("usuario_id", usuario_id).execute()
