from datetime import datetime

from fastapi import HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import ExpiredSignatureError, JWTError, jwt

from app.config.settings import JWT_ALGORITHM, JWT_SECRET
from app.repositories.token_repository import TokenRepository
from app.repositories.usuario_repository import UsuarioRepository

security = HTTPBearer()
_tokens = TokenRepository()
_usuarios = UsuarioRepository()


def _validar_usuario_ativo(usuario_id: str) -> dict:
    usuario = _usuarios.buscar_por_id(usuario_id)
    if not usuario:
        raise HTTPException(status_code=401, detail="Usuário não encontrado")
    if usuario.get("ativo") is False:
        raise HTTPException(status_code=403, detail="Usuário inativo")
    return usuario


def obter_token_payload(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> dict:
    token = credentials.credentials

    try:
        payload = jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Sessão expirada — faça login novamente")
    except JWTError:
        raise HTTPException(status_code=401, detail="Token inválido")

    token_type = payload.get("type")
    if token_type and token_type != "access":
        raise HTTPException(status_code=401, detail="Token inválido")

    user_id = payload.get("sub")
    if not user_id:
        raise HTTPException(status_code=401, detail="Token inválido")

    jti = payload.get("jti")
    if jti:
        try:
            _tokens.limpar_revogados_expirados()
            if _tokens.jti_revogado(jti):
                raise HTTPException(status_code=401, detail="Sessão encerrada")
        except HTTPException:
            raise
        except Exception:
            pass

    usuario = _validar_usuario_ativo(str(user_id))

    return {
        "sub": str(user_id),
        "email": usuario.get("email") or payload.get("email"),
        "role": usuario.get("perfil") or "user",
        "jti": jti,
        "exp": payload.get("exp"),
    }


def verificar_token(payload: dict = Depends(obter_token_payload)) -> dict:
    return payload


def obter_usuario_id(payload: dict = Depends(obter_token_payload)) -> str:
    return payload.get("sub", "")


def obter_usuario_atual(payload: dict = Depends(obter_token_payload)) -> dict:
    return _validar_usuario_ativo(payload.get("sub", ""))


def obter_workspace_context(usuario: dict = Depends(obter_usuario_atual)) -> dict:
    from app.services.workspace_service import workspace_service

    return workspace_service.get_current_workspace_context(usuario)


def requer_admin(payload: dict = Depends(obter_token_payload)) -> dict:
    if payload.get("role") != "admin":
        raise HTTPException(status_code=403, detail="Apenas administradores podem executar esta ação")
    return payload


def revogar_access_token(token: str) -> None:
    try:
        payload = jwt.decode(
            token,
            JWT_SECRET,
            algorithms=[JWT_ALGORITHM],
            options={"verify_exp": False},
        )
    except JWTError:
        return

    jti = payload.get("jti")
    if not jti:
        return

    exp = payload.get("exp")
    if isinstance(exp, (int, float)):
        expira = datetime.utcfromtimestamp(exp)
    else:
        expira = datetime.utcnow()

    _tokens.revogar_jti(jti, str(payload.get("sub") or ""), expira)
