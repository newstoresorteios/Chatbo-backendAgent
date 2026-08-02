import logging

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials

from app.core.auth import obter_usuario_atual, obter_usuario_id, security
from app.schemas.auth import (
    ForgotPasswordRequest,
    LoginRequest,
    LogoutRequest,
    RefreshTokenRequest,
    RegisterRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
)
from app.services.auth_service import AuthService

router = APIRouter()
auth_service = AuthService()
logger = logging.getLogger(__name__)


@router.post("/login")
def login(credentials: LoginRequest):
    return auth_service.login(
        email=credentials.email,
        password=credentials.password,
    )


@router.post("/register")
def register(body: RegisterRequest):
    try:
        return auth_service.register(
            name=body.name,
            email=body.email,
            password=body.password,
            company=body.company,
        )
    except HTTPException:
        raise
    except RuntimeError as exc:
        logger.exception("Falha de configuracao no cadastro empresarial")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Configuracao Supabase ausente ou invalida.",
        ) from exc
    except Exception as exc:
        logger.exception("Falha ao concluir cadastro empresarial")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Nao foi possivel concluir o cadastro.",
        ) from exc


@router.post("/refresh")
def refresh(body: RefreshTokenRequest):
    return auth_service.refresh(body.refreshToken)


@router.get("/me")
def me(usuario: dict = Depends(obter_usuario_atual)):
    return auth_service._mapear_usuario(usuario)


@router.post("/logout")
def logout(
    body: LogoutRequest | None = None,
    usuario_id: str = Depends(obter_usuario_id),
    credentials: HTTPAuthorizationCredentials = Depends(security),
):
    refresh_token = body.refreshToken if body else None
    return auth_service.logout(
        access_token=credentials.credentials,
        usuario_id=usuario_id,
        refresh_token=refresh_token,
    )


@router.post("/forgot-password")
def forgot_password(body: ForgotPasswordRequest):
    return auth_service.solicitar_reset_senha(body.email)


@router.post("/reset-password")
def reset_password(body: ResetPasswordRequest):
    return auth_service.redefinir_senha(body.token, body.password)


@router.patch("/profile")
def update_profile(
    body: UpdateProfileRequest,
    usuario_id: str = Depends(obter_usuario_id),
):
    return auth_service.atualizar_perfil(
        usuario_id=usuario_id,
        name=body.name,
        company=body.company,
    )
