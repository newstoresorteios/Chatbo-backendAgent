from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.auth import obter_usuario_atual
from app.schemas.ai.common import FlexibleModel
from app.services.ai.resources import (
    conversation_statuses_service,
    remarketing_attempts_service,
    remarketing_contacts_service,
)

router = APIRouter()


@router.get("/remarketing/contacts")
def listar_contacts(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    channel: str | None = None,
    marketingStatus: str | None = None,
    search: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if channel:
        filters["channel"] = channel
    if marketingStatus:
        filters["marketing_status"] = marketingStatus
    return remarketing_contacts_service.listar(
        usuario,
        page=page,
        page_size=pageSize,
        filters=filters,
        search_column="sender_name" if search else None,
        search=search,
    )


@router.post("/remarketing/contacts")
def criar_contact(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return remarketing_contacts_service.criar(usuario, body.to_db())


@router.patch("/remarketing/contacts/{record_id}")
def atualizar_contact(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return remarketing_contacts_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))


@router.get("/conversation-statuses")
def listar_statuses(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    contactId: int | None = None,
    status: str | None = None,
    stage: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if contactId is not None:
        filters["contact_id"] = contactId
    if status:
        filters["status"] = status
    if stage:
        filters["stage"] = stage
    return conversation_statuses_service.listar(
        usuario,
        page=page,
        page_size=pageSize,
        filters=filters,
    )


@router.post("/conversation-statuses")
def criar_status(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return conversation_statuses_service.criar(usuario, body.to_db())


@router.patch("/conversation-statuses/{record_id}")
def atualizar_status(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return conversation_statuses_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))


@router.get("/remarketing/attempts")
def listar_attempts(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    conversationStatusId: int | None = None,
    status: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if conversationStatusId is not None:
        filters["conversation_status_id"] = conversationStatusId
    if status:
        filters["status"] = status
    return remarketing_attempts_service.listar(
        usuario,
        page=page,
        page_size=pageSize,
        filters=filters,
    )


@router.post("/remarketing/attempts")
def criar_attempt(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return remarketing_attempts_service.criar(usuario, body.to_db())


@router.patch("/remarketing/attempts/{record_id}")
def atualizar_attempt(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return remarketing_attempts_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))
