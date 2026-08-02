from datetime import datetime

from app.services.supabase_service import supabase


class SettingsRepository:

    def obter_empresa(self) -> dict | None:
        resposta = (
            supabase
            .table("empresa_config")
            .select("*")
            .eq("id", "default")
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def salvar_empresa(self, dados: dict) -> dict:
        existente = self.obter_empresa()
        payload = {**dados, "updated_at": datetime.utcnow().isoformat()}

        if existente:
            resposta = (
                supabase
                .table("empresa_config")
                .update(payload)
                .eq("id", "default")
                .execute()
            )
        else:
            resposta = (
                supabase
                .table("empresa_config")
                .insert({"id": "default", **payload})
                .execute()
            )

        rows = resposta.data or []
        return rows[0] if rows else {"id": "default", **payload}

    def obter_preferencias(self, usuario_id: str) -> dict:
        resposta = (
            supabase
            .table("usuarios")
            .select("preferencias")
            .eq("id", usuario_id)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        if not rows:
            return {}
        prefs = rows[0].get("preferencias")
        return prefs if isinstance(prefs, dict) else {}

    def salvar_preferencias(self, usuario_id: str, preferencias: dict) -> dict:
        resposta = (
            supabase
            .table("usuarios")
            .update({
                "preferencias": preferencias,
                "updated_at": datetime.utcnow().isoformat(),
            })
            .eq("id", usuario_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0].get("preferencias", preferencias) if rows else preferencias
