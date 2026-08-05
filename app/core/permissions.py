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

_PERFIL_RANK = {
    "user": 0,
    "vendedor": 1,
    "supervisor": 2,
    "admin": 3,
}


def tem_permissao(role: str | None, chave: str) -> bool:
    role_key = (role or "user").strip().lower()
    perms = ROLE_PERMISSIONS.get(role_key, ROLE_PERMISSIONS["user"])
    return bool(perms.get(chave))


def perfil_efetivo(usuario: dict) -> str:
    """Usa o maior privilégio entre perfil JWT e papel no workspace."""
    candidates = [(usuario.get("perfil") or "user").strip().lower()]

    try:
        from app.services.workspace_service import workspace_service

        context = workspace_service.get_current_workspace_context(usuario)
        mapped = WORKSPACE_ROLE_TO_PERFIL.get(context.get("workspaceRole") or "")
        if mapped:
            candidates.append(mapped)
        # System admin da plataforma sempre opera como admin no console de empresa.
        if (usuario.get("account_type") or "") == "system_admin":
            candidates.append("admin")
    except Exception:
        pass

    return max(candidates, key=lambda role: _PERFIL_RANK.get(role, 0))


def requer_permissao(chave: str):
    def dependency(usuario: dict = Depends(obter_usuario_atual)) -> dict:
        if not tem_permissao(perfil_efetivo(usuario), chave):
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para executar esta ação",
            )
        return usuario

    return dependency
