from fastapi import APIRouter, Depends

from app.core.auth import obter_usuario_atual
from app.schemas.persona import AgentPersonaCreate, AgentPersonaUpdate, PersonaTestRequest
from app.services.persona_service import persona_service

router = APIRouter()


@router.get("/personas")
def listar_personas(usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.listar(usuario)


@router.post("/personas")
def criar_persona(body: AgentPersonaCreate, usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.criar(usuario, body.model_dump())


@router.get("/personas/{persona_id}")
def obter_persona(persona_id: str, usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.obter(usuario, persona_id)


@router.patch("/personas/{persona_id}")
def atualizar_persona(
    persona_id: str,
    body: AgentPersonaUpdate,
    usuario: dict = Depends(obter_usuario_atual),
):
    return persona_service.atualizar(usuario, persona_id, body.model_dump(exclude_unset=True))


@router.post("/personas/{persona_id}/activate")
def ativar_persona(persona_id: str, usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.ativar(usuario, persona_id)


@router.post("/personas/{persona_id}/deactivate")
def desativar_persona(persona_id: str, usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.desativar(usuario, persona_id)


@router.get("/personas/{persona_id}/versions")
def listar_versoes_persona(persona_id: str, usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.listar_versoes(usuario, persona_id)


@router.get("/personas/{persona_id}/versions/{version}")
def obter_versao_persona(persona_id: str, version: int, usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.obter_versao(usuario, persona_id, version)


@router.post("/personas/test")
def testar_persona(body: PersonaTestRequest, usuario: dict = Depends(obter_usuario_atual)):
    return persona_service.testar(usuario, body.model_dump())
