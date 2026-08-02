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
    context = workspace_service.get_current_workspace_context(usuario)
    role_map = {
        "owner": "admin",
        "admin": "admin",
        "supervisor": "supervisor",
        "seller": "vendedor",
        "member": "user",
    }
    return settings_service.permissoes_do_perfil(role_map.get(context.get("workspaceRole"), usuario.get("perfil") or "user"))


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
