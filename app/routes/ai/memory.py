from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.auth import obter_usuario_atual
from app.schemas.ai.common import FlexibleModel
from app.services.ai.resources import (
    contact_memories_service,
    conversation_summaries_service,
    memory_proposals_service,
    user_preferences_service,
)

router = APIRouter()


@router.get("/user-preferences/{user_id}")
def obter_user_preferences(user_id: int, usuario: dict = Depends(obter_usuario_atual)):
    return user_preferences_service.obter_por(usuario, {"user_id": user_id})


@router.put("/user-preferences/{user_id}")
def upsert_user_preferences(
    user_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return user_preferences_service.put_por(usuario, {"user_id": user_id}, body.to_db(exclude_none=True))


@router.get("/contact-memories")
def listar_contact_memories(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    senderKey: str | None = None,
    status: str | None = None,
    memoryKind: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if senderKey:
        filters["sender_key"] = senderKey
    if status:
        filters["status"] = status
    if memoryKind:
        filters["memory_kind"] = memoryKind
    return contact_memories_service.listar(usuario, page=page, page_size=pageSize, filters=filters)


@router.post("/contact-memories")
def criar_contact_memory(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return contact_memories_service.criar(usuario, body.to_db())


@router.patch("/contact-memories/{record_id}")
def atualizar_contact_memory(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return contact_memories_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))


@router.get("/conversation-summaries/{conversation_key}")
def obter_conversation_summary(
    conversation_key: str,
    tenantId: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {"conversation_key": conversation_key}
    if tenantId:
        filters["tenant_id"] = tenantId
    return conversation_summaries_service.obter_por(usuario, filters)


@router.put("/conversation-summaries/{conversation_key}")
def upsert_conversation_summary(
    conversation_key: str,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    payload = body.to_db(exclude_none=True)
    filters = {"conversation_key": conversation_key}
    if payload.get("tenant_id"):
        filters["tenant_id"] = payload["tenant_id"]
    return conversation_summaries_service.put_por(usuario, filters, payload)


@router.get("/memory-proposals")
def listar_memory_proposals(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    status: str | None = None,
    proposalType: str | None = None,
    senderKey: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status
    if proposalType:
        filters["proposal_type"] = proposalType
    if senderKey:
        filters["sender_key"] = senderKey
    return memory_proposals_service.listar(usuario, page=page, page_size=pageSize, filters=filters)


@router.post("/memory-proposals")
def criar_memory_proposal(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return memory_proposals_service.criar(usuario, body.to_db())


@router.patch("/memory-proposals/{record_id}")
def atualizar_memory_proposal(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return memory_proposals_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))
