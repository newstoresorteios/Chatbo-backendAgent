from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import obter_token_payload, obter_usuario_atual
from app.schemas.workspace import WorkspaceSettingsUpdate
from app.services.settings_service import settings_service
from app.services.workspace_service import workspace_service

router = APIRouter()


class NotificationSettingsRequest(BaseModel):
    email: bool = True
    push: bool = True
    newMessage: bool = True
    newLead: bool = False
    dailyReport: bool = True


class ChangePasswordRequest(BaseModel):
    currentPassword: str = Field(min_length=1)
    newPassword: str = Field(min_length=6)


@router.get("/settings/empresa")
def obter_empresa(usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.obter_empresa_settings(usuario)


@router.patch("/settings/empresa")
def salvar_empresa(
    body: WorkspaceSettingsUpdate,
    usuario: dict = Depends(obter_usuario_atual),
):
    return workspace_service.salvar_empresa_settings(usuario, body.model_dump(exclude_unset=True))


@router.get("/settings/preferencias")
def obter_preferencias(payload: dict = Depends(obter_token_payload)):
    return settings_service.obter_preferencias(payload["sub"])


@router.patch("/settings/preferencias")
def salvar_preferencias(
    body: NotificationSettingsRequest,
    payload: dict = Depends(obter_token_payload),
):
    return settings_service.salvar_preferencias(
        payload["sub"],
        body.model_dump(),
    )


@router.get("/settings/permissoes")
def obter_permissoes(usuario: dict = Depends(obter_usuario_atual)):
    from app.core.permissions import perfil_efetivo

    return settings_service.permissoes_do_perfil(perfil_efetivo(usuario))


@router.get("/settings/brevo")
def obter_status_brevo(usuario: dict = Depends(obter_usuario_atual)):
    """Diagnóstico do envio Brevo (mesmo canal do NSAgent)."""
    from app.core.permissions import perfil_efetivo, tem_permissao
    from app.services.brevo_outbound_service import brevo_outbound_service
    from fastapi import HTTPException

    if not tem_permissao(perfil_efetivo(usuario), "managePlatform"):
        raise HTTPException(status_code=403, detail="Sem permissão")
    return brevo_outbound_service.status()


@router.post("/settings/alterar-senha")
def alterar_senha(
    body: ChangePasswordRequest,
    payload: dict = Depends(obter_token_payload),
):
    return settings_service.alterar_senha(
        payload["sub"],
        current_password=body.currentPassword,
        new_password=body.newPassword,
    )
