from fastapi import Depends, HTTPException

from app.core.auth import obter_usuario_atual
from app.services.settings_service import ROLE_PERMISSIONS

WORKSPACE_ROLE_TO_PERFIL = {
    "owner": "admin",
    "admin": "admin",
    "supervisor": "supervisor",
    "seller": "vendedor",
    "member": "user",
}


def tem_permissao(role: str | None, chave: str) -> bool:
    role_key = (role or "user").strip().lower()
    perms = ROLE_PERMISSIONS.get(role_key, ROLE_PERMISSIONS["user"])
    return bool(perms.get(chave))


def perfil_efetivo(usuario: dict) -> str:
    """Resolve perfil de permissão a partir do papel no workspace (company)."""
    from app.services.workspace_service import workspace_service

    try:
        context = workspace_service.get_current_workspace_context(usuario)
        mapped = WORKSPACE_ROLE_TO_PERFIL.get(context.get("workspaceRole") or "")
        if mapped:
            return mapped
    except Exception:
        pass
    return (usuario.get("perfil") or "user").strip().lower()


def requer_permissao(chave: str):
    def dependency(usuario: dict = Depends(obter_usuario_atual)) -> dict:
        if not tem_permissao(perfil_efetivo(usuario), chave):
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para executar esta ação",
            )
        return usuario

    return dependency
