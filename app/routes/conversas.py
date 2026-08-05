from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import obter_token_payload, obter_usuario_atual
from app.core.workspace_scope import obter_company_context, workspace_id_from_context
from app.repositories.usuario_repository import UsuarioRepository
from app.services.conversation_agent_context_service import ConversationAgentContextService
from app.services.conversas_service import ConversasService

router = APIRouter()
conversas_service = ConversasService()
conversation_agent_context_service = ConversationAgentContextService()


class SendMessageRequest(BaseModel):
    content: str = Field(min_length=1)
    sender: str = "agent"


class TransferRequest(BaseModel):
    assigneeId: str = Field(min_length=1)


class CloseRequest(BaseModel):
    note: str | None = None


class ReserveProductRequest(BaseModel):
    productId: str = Field(min_length=1)
    productName: str | None = None
    quantity: int = Field(default=1, ge=1, le=999)


def _actor_name(payload: dict) -> str:
    usuario = UsuarioRepository().buscar_por_id(payload["sub"])
    if usuario:
        return usuario.get("nome") or payload.get("email") or "Atendente"
    return payload.get("email") or "Atendente"


@router.get("/conversas")
def get_conversas(context: dict = Depends(obter_company_context)):
    return conversas_service.listar_conversas(
        workspace_id=workspace_id_from_context(context),
    )


@router.get("/conversas/{conversation_id}/mensagens")
def get_mensagens(
    conversation_id: str,
    context: dict = Depends(obter_company_context),
):
    return conversas_service.listar_mensagens(
        conversation_id,
        workspace_id=workspace_id_from_context(context),
    )


@router.get("/conversas/{conversation_id}/agente")
def get_conversa_agente(
    conversation_id: str,
    usuario: dict = Depends(obter_usuario_atual),
    context: dict = Depends(obter_company_context),
):
    """Contexto AI agregado (funil, memórias, PIX, decisões) para o painel de atendimento."""
    return conversation_agent_context_service.obter(
        conversation_id,
        usuario,
        workspace_id_from_context(context),
    )


@router.post("/conversas/{conversation_id}/mensagens")
def send_mensagem(
    conversation_id: str,
    body: SendMessageRequest,
    payload: dict = Depends(obter_token_payload),
    context: dict = Depends(obter_company_context),
):
    return conversas_service.enviar_mensagem(
        conversation_id,
        body.content,
        body.sender,
        workspace_id=workspace_id_from_context(context),
        actor_user_id=payload.get("sub"),
        actor_name=_actor_name(payload),
    )


@router.patch("/conversas/{conversation_id}/transferir")
def transferir_conversa(
    conversation_id: str,
    body: TransferRequest,
    payload: dict = Depends(obter_token_payload),
    context: dict = Depends(obter_company_context),
):
    return conversas_service.transferir(
        conversation_id,
        body.assigneeId,
        _actor_name(payload),
        workspace_id=workspace_id_from_context(context),
    )


@router.patch("/conversas/{conversation_id}/assumir")
def assumir_conversa(
    conversation_id: str,
    payload: dict = Depends(obter_token_payload),
    context: dict = Depends(obter_company_context),
):
    return conversas_service.assumir(
        conversation_id,
        payload["sub"],
        _actor_name(payload),
        workspace_id=workspace_id_from_context(context),
    )


@router.patch("/conversas/{conversation_id}/encerrar")
def encerrar_conversa(
    conversation_id: str,
    body: CloseRequest | None = None,
    payload: dict = Depends(obter_token_payload),
    context: dict = Depends(obter_company_context),
):
    note = body.note if body else None
    return conversas_service.encerrar(
        conversation_id,
        _actor_name(payload),
        note,
        workspace_id=workspace_id_from_context(context),
    )


@router.patch("/conversas/{conversation_id}/reativar")
def reativar_conversa(
    conversation_id: str,
    payload: dict = Depends(obter_token_payload),
    context: dict = Depends(obter_company_context),
):
    return conversas_service.reativar(
        conversation_id,
        _actor_name(payload),
        workspace_id=workspace_id_from_context(context),
    )


@router.post("/conversas/{conversation_id}/reserva")
def reservar_produto(
    conversation_id: str,
    body: ReserveProductRequest,
    payload: dict = Depends(obter_token_payload),
    context: dict = Depends(obter_company_context),
):
    return conversas_service.reservar_produto(
        conversation_id,
        body.productId,
        body.productName or body.productId,
        _actor_name(payload),
        body.quantity,
        workspace_id=workspace_id_from_context(context),
    )
