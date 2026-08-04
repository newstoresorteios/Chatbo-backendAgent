from fastapi import APIRouter, Depends

from app.core.auth import obter_usuario_atual
from app.schemas.agent_registry import WorkspaceAgentUpdate
from app.services.agent_registry_service import agent_registry_service

router = APIRouter()


@router.get("/agents/types")
def listar_tipos_agente(usuario: dict = Depends(obter_usuario_atual)):
    _ = usuario
    return agent_registry_service.listar_tipos()


@router.get("/agents/current")
def obter_agente_atual(usuario: dict = Depends(obter_usuario_atual)):
    return agent_registry_service.obter_agente_empresa(usuario)


@router.put("/agents/current")
def atualizar_agente_atual(
    body: WorkspaceAgentUpdate,
    usuario: dict = Depends(obter_usuario_atual),
):
    return agent_registry_service.atualizar_agente_empresa(
        usuario,
        body.model_dump(exclude_unset=True),
    )
