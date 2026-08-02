from fastapi import Depends, HTTPException

from app.core.auth import obter_token_payload
from app.services.settings_service import ROLE_PERMISSIONS


def tem_permissao(role: str | None, chave: str) -> bool:
    role_key = (role or "user").strip().lower()
    perms = ROLE_PERMISSIONS.get(role_key, ROLE_PERMISSIONS["user"])
    return bool(perms.get(chave))


def requer_permissao(chave: str):
    def dependency(payload: dict = Depends(obter_token_payload)) -> dict:
        if not tem_permissao(payload.get("role"), chave):
            raise HTTPException(
                status_code=403,
                detail="Você não tem permissão para executar esta ação",
            )
        return payload

    return dependency
