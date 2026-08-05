from fastapi import HTTPException

from app.core.password import hash_senha, verificar_senha
from app.repositories.settings_repository import SettingsRepository
from app.repositories.usuario_repository import UsuarioRepository

DEFAULT_NOTIFICATIONS = {
    "email": True,
    "push": True,
    "newMessage": True,
    "newLead": False,
    "dailyReport": True,
}

ROLE_PERMISSIONS: dict[str, dict[str, bool]] = {
    "admin": {
        "viewReports": True,
        "viewFinancial": True,
        "manageUsers": True,
        "manageIntegrations": True,
        "managePlatform": True,
        "exportData": True,
    },
    "supervisor": {
        "viewReports": True,
        "viewFinancial": True,
        "manageUsers": False,
        "manageIntegrations": True,
        "managePlatform": True,
        "exportData": True,
    },
    "vendedor": {
        "viewReports": False,
        "viewFinancial": False,
        "manageUsers": False,
        "manageIntegrations": False,
        "managePlatform": False,
        "exportData": False,
    },
    "user": {
        "viewReports": False,
        "viewFinancial": False,
        "manageUsers": False,
        "manageIntegrations": False,
        "managePlatform": False,
        "exportData": False,
    },
}


class SettingsService:

    def __init__(self):
        self.repo = SettingsRepository()
        self.usuarios = UsuarioRepository()

    def _map_empresa(self, row: dict | None) -> dict:
        row = row or {}
        return {
            "name": row.get("nome") or "PulseDesk",
            "cnpj": row.get("cnpj") or "",
            "email": row.get("email") or "",
            "phone": row.get("telefone") or "",
        }

    def obter_empresa(self) -> dict:
        try:
            return self._map_empresa(self.repo.obter_empresa())
        except Exception as exc:
            if "empresa_config" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail="Execute supabase/007_settings.sql no Supabase.",
                ) from exc
            raise

    def salvar_empresa(self, *, name: str, cnpj: str | None, email: str | None, phone: str | None) -> dict:
        if not name.strip():
            raise HTTPException(status_code=400, detail="Nome da empresa é obrigatório")

        row = self.repo.salvar_empresa({
            "nome": name.strip(),
            "cnpj": (cnpj or "").strip() or None,
            "email": (email or "").strip() or None,
            "telefone": (phone or "").strip() or None,
        })
        return self._map_empresa(row)

    def obter_preferencias(self, usuario_id: str) -> dict:
        try:
            stored = self.repo.obter_preferencias(usuario_id)
        except Exception as exc:
            if "preferencias" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail="Execute supabase/007_settings.sql no Supabase.",
                ) from exc
            raise

        notifications = {**DEFAULT_NOTIFICATIONS, **(stored.get("notifications") or {})}
        return {"notifications": notifications}

    def salvar_preferencias(self, usuario_id: str, notifications: dict) -> dict:
        merged = {**DEFAULT_NOTIFICATIONS, **notifications}
        for key in DEFAULT_NOTIFICATIONS:
            if key in notifications:
                merged[key] = bool(notifications[key])

        prefs = self.repo.salvar_preferencias(usuario_id, {"notifications": merged})
        return {"notifications": prefs.get("notifications", merged)}

    def permissoes_do_perfil(self, role: str) -> dict:
        role_key = (role or "user").lower()
        base = ROLE_PERMISSIONS.get(role_key, ROLE_PERMISSIONS["user"])
        # Cópia defensiva + garante chaves novas mesmo com cache/deploy parcial.
        perms = {
            "viewReports": False,
            "viewFinancial": False,
            "manageUsers": False,
            "manageIntegrations": False,
            "managePlatform": False,
            "exportData": False,
            **base,
        }
        if role_key == "admin":
            perms = {key: True for key in perms}
        elif role_key == "supervisor":
            perms["viewFinancial"] = True
            perms["viewReports"] = True
            perms["managePlatform"] = True
            perms["manageIntegrations"] = True
        return {
            "role": role_key,
            "permissions": perms,
            "labels": {
                "viewReports": "Visualizar relatórios",
                "viewFinancial": "Ver painel comercial, pedidos e funil",
                "manageUsers": "Gerenciar usuários",
                "manageIntegrations": "Gerenciar integrações e sincronização",
                "managePlatform": "Gerenciar canais, campanhas, persona e robô",
                "exportData": "Exportar dados",
            },
        }

    def alterar_senha(
        self,
        usuario_id: str,
        *,
        current_password: str,
        new_password: str,
    ) -> dict:
        if len(new_password) < 6:
            raise HTTPException(status_code=400, detail="Nova senha deve ter no mínimo 6 caracteres")

        usuario = self.usuarios.buscar_por_id(usuario_id)
        if not usuario:
            raise HTTPException(status_code=404, detail="Usuário não encontrado")

        senha_hash = usuario.get("senha_hash") or ""
        if not verificar_senha(current_password, senha_hash):
            raise HTTPException(status_code=400, detail="Senha atual incorreta")

        self.usuarios.atualizar(usuario_id, {"senha_hash": hash_senha(new_password)})
        return {"success": True, "message": "Senha alterada com sucesso"}


settings_service = SettingsService()
