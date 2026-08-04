from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.auth import obter_usuario_atual
from app.schemas.ai.common import FlexibleModel
from app.services.ai.resources import agent_responses_service, inbound_messages_service

router = APIRouter()


@router.get("/inbound-messages")
def listar_inbound_messages(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    channel: str | None = None,
    senderKey: str | None = None,
    conversationId: str | None = None,
    search: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if channel:
        filters["channel"] = channel
    if senderKey:
        filters["sender_key"] = senderKey
    if conversationId:
        filters["conversation_id"] = conversationId
    return inbound_messages_service.listar(
        usuario,
        page=page,
        page_size=pageSize,
        filters=filters,
        search_column="text" if search else None,
        search=search,
    )


@router.post("/inbound-messages")
def criar_inbound_message(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return inbound_messages_service.criar(usuario, body.to_db())


@router.get("/inbound-messages/{record_id}")
def obter_inbound_message(record_id: int, usuario: dict = Depends(obter_usuario_atual)):
    return inbound_messages_service.obter(usuario, record_id)


@router.get("/agent-responses")
def listar_agent_responses(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    inboundId: int | None = None,
    channel: str | None = None,
    senderKey: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if inboundId is not None:
        filters["inbound_id"] = inboundId
    if channel:
        filters["channel"] = channel
    if senderKey:
        filters["sender_key"] = senderKey
    return agent_responses_service.listar(
        usuario,
        page=page,
        page_size=pageSize,
        filters=filters,
    )


@router.post("/agent-responses")
def criar_agent_response(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return agent_responses_service.criar(usuario, body.to_db())


@router.get("/agent-responses/{record_id}")
def obter_agent_response(record_id: int, usuario: dict = Depends(obter_usuario_atual)):
    return agent_responses_service.obter(usuario, record_id)
