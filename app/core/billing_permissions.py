from fastapi import Depends, HTTPException

from app.core.auth import obter_token_payload
from app.repositories.usuario_repository import UsuarioRepository


_usuarios = UsuarioRepository()


def requer_system_admin(payload: dict = Depends(obter_token_payload)) -> dict:
    usuario = _usuarios.buscar_por_id(str(payload.get("sub") or ""))
    if not usuario or usuario.get("account_type") != "system_admin":
        raise HTTPException(status_code=403, detail="Apenas administradores globais podem acessar esta área.")
    return usuario
