from fastapi import APIRouter, Depends, Query

from app.core.auth import obter_usuario_atual
from app.schemas.agent_registry import AgentConfigurationPublish, WorkspaceAgentUpdate
from app.services.agent_registry_service import agent_registry_service
from app.services.agent_trace_service import agent_trace_service

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


@router.get("/agents/current/configuration")
def obter_configuracao_agente(usuario: dict = Depends(obter_usuario_atual)):
    return agent_registry_service.obter_configuracao(usuario)


@router.put("/agents/current/configuration")
def publicar_configuracao_agente(
    body: AgentConfigurationPublish,
    usuario: dict = Depends(obter_usuario_atual),
):
    return agent_registry_service.publicar_configuracao(
        usuario,
        body.model_dump(),
    )


@router.get("/agents/current/configuration/history")
def listar_historico_configuracao(usuario: dict = Depends(obter_usuario_atual)):
    return agent_registry_service.listar_historico_configuracao(usuario)


@router.get("/agents/current/traces")
def listar_execucoes_agente(
    limit: int = Query(default=40, ge=1, le=100),
    before: str | None = Query(default=None, max_length=80),
    channel: str | None = Query(default=None, max_length=40),
    outcome: str | None = Query(default=None, pattern="^(delivered|fallback|handoff|failed)$"),
    usuario: dict = Depends(obter_usuario_atual),
):
    return agent_trace_service.listar(
        usuario,
        limit=limit,
        before=before,
        channel=channel,
        outcome=outcome,
    )


@router.get("/agents/current/traces/{response_id}")
def obter_execucao_agente(
    response_id: int,
    usuario: dict = Depends(obter_usuario_atual),
):
    return agent_trace_service.obter(usuario, response_id)
