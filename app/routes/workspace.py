from fastapi import APIRouter, Depends

from app.core.auth import obter_usuario_atual
from app.schemas.workspace import OnboardingTestRequest, OnboardingUpdate, WorkspaceChannelUpdate
from app.services.workspace_service import workspace_service

router = APIRouter()


@router.get("/workspace/current")
def obter_workspace_atual(usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.obter_workspace_atual(usuario)


@router.get("/onboarding")
def obter_onboarding(usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.obter_onboarding(usuario)


@router.patch("/onboarding")
def atualizar_onboarding(
    body: OnboardingUpdate,
    usuario: dict = Depends(obter_usuario_atual),
):
    return workspace_service.atualizar_onboarding(
        usuario,
        body.model_dump(exclude_unset=True),
    )


@router.post("/onboarding/complete")
def concluir_onboarding(usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.concluir_onboarding(usuario)


@router.post("/onboarding/activate")
def ativar_onboarding(usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.ativar_onboarding(usuario)


@router.post("/onboarding/test")
def testar_onboarding(body: OnboardingTestRequest, usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.testar_onboarding(usuario, body.inputText)


@router.get("/workspace/channels")
def listar_canais(usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.listar_canais(usuario)


@router.put("/workspace/channels")
def salvar_canal(body: WorkspaceChannelUpdate, usuario: dict = Depends(obter_usuario_atual)):
    return workspace_service.salvar_canal(usuario, body.model_dump())
