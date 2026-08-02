from datetime import datetime

from app.services.supabase_service import supabase


class MercosSyncRepository:

    def registrar(
        self,
        *,
        tipo: str,
        mensagem: str,
        status: str = "success",
        quantidade: int = 0,
        resumo: dict | None = None,
        cursor_ultima_alteracao: str | None = None,
    ) -> dict | None:
        payload_resumo = dict(resumo or {})
        if cursor_ultima_alteracao:
            payload_resumo["cursor_ultima_alteracao"] = cursor_ultima_alteracao

        payload = {
            "tipo": tipo,
            "status": status,
            "mensagem": mensagem,
            "quantidade": quantidade,
            "resumo": payload_resumo or None,
            "created_at": datetime.utcnow().isoformat(),
        }
        try:
            resposta = supabase.table("mercos_sync_logs").insert(payload).execute()
            rows = resposta.data or []
            return rows[0] if rows else payload
        except Exception:
            return None

    def ultima_sincronizacao(self, tipo: str) -> str | None:
        """Cursor preferencial: maior ultima_alteracao da Mercos salva no resumo.

        Fallback: created_at do último log de sucesso (compatível com logs antigos).
        """
        try:
            resposta = (
                supabase
                .table("mercos_sync_logs")
                .select("created_at,resumo")
                .eq("tipo", tipo)
                .eq("status", "success")
                .order("created_at", desc=True)
                .limit(1)
                .execute()
            )
            rows = resposta.data or []
            if not rows:
                return None
            row = rows[0]
            resumo = row.get("resumo") or {}
            if isinstance(resumo, dict):
                cursor = resumo.get("cursor_ultima_alteracao")
                if cursor:
                    return str(cursor)
            return row.get("created_at")
        except Exception:
            return None

    def listar_recentes(self, limite: int = 10) -> list[dict]:
        try:
            resposta = (
                supabase
                .table("mercos_sync_logs")
                .select("*")
                .order("created_at", desc=True)
                .limit(limite)
                .execute()
            )
            return resposta.data or []
        except Exception:
            return []
