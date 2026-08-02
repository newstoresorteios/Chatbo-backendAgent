from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.core.auth import obter_token_payload, verificar_token
from app.repositories.usuario_repository import UsuarioRepository
from app.services.conversas_service import ConversasService

router = APIRouter()
conversas_service = ConversasService()


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
def get_conversas(autorizado=Depends(verificar_token)):
    return conversas_service.listar_conversas()


@router.get("/conversas/{conversation_id}/mensagens")
def get_mensagens(conversation_id: str, autorizado=Depends(verificar_token)):
    return conversas_service.listar_mensagens(conversation_id)


@router.post("/conversas/{conversation_id}/mensagens")
def send_mensagem(
    conversation_id: str,
    body: SendMessageRequest,
    autorizado=Depends(verificar_token),
):
    return conversas_service.enviar_mensagem(
        conversation_id,
        body.content,
        body.sender,
    )


@router.patch("/conversas/{conversation_id}/transferir")
def transferir_conversa(
    conversation_id: str,
    body: TransferRequest,
    payload: dict = Depends(obter_token_payload),
):
    return conversas_service.transferir(
        conversation_id,
        body.assigneeId,
        _actor_name(payload),
    )


@router.patch("/conversas/{conversation_id}/assumir")
def assumir_conversa(
    conversation_id: str,
    payload: dict = Depends(obter_token_payload),
):
    return conversas_service.assumir(
        conversation_id,
        payload["sub"],
        _actor_name(payload),
    )


@router.patch("/conversas/{conversation_id}/encerrar")
def encerrar_conversa(
    conversation_id: str,
    body: CloseRequest | None = None,
    payload: dict = Depends(obter_token_payload),
):
    note = body.note if body else None
    return conversas_service.encerrar(conversation_id, _actor_name(payload), note)


@router.patch("/conversas/{conversation_id}/reativar")
def reativar_conversa(
    conversation_id: str,
    payload: dict = Depends(obter_token_payload),
):
    return conversas_service.reativar(conversation_id, _actor_name(payload))


@router.post("/conversas/{conversation_id}/reserva")
def reservar_produto(
    conversation_id: str,
    body: ReserveProductRequest,
    payload: dict = Depends(obter_token_payload),
):
    return conversas_service.reservar_produto(
        conversation_id,
        body.productId,
        body.productName or body.productId,
        _actor_name(payload),
        body.quantity,
    )
