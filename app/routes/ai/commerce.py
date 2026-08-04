from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.auth import obter_usuario_atual
from app.schemas.ai.common import FlexibleModel
from app.services.ai.resources import (
    commerce_sessions_service,
    identity_links_service,
    pix_payments_service,
)

router = APIRouter()


@router.get("/identity-links")
def listar_identity_links(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    personKey: str | None = None,
    identityType: str | None = None,
    channel: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if personKey:
        filters["person_key"] = personKey
    if identityType:
        filters["identity_type"] = identityType
    if channel:
        filters["channel"] = channel
    return identity_links_service.listar(usuario, page=page, page_size=pageSize, filters=filters)


@router.post("/identity-links")
def criar_identity_link(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return identity_links_service.criar(usuario, body.to_db())


@router.get("/commerce-sessions/{person_key}")
def obter_commerce_session(person_key: str, usuario: dict = Depends(obter_usuario_atual)):
    return commerce_sessions_service.obter(usuario, person_key)


@router.put("/commerce-sessions/{person_key}")
def upsert_commerce_session(
    person_key: str,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    payload = body.to_db(exclude_none=True)
    payload["person_key"] = person_key
    return commerce_sessions_service.upsert(usuario, payload, on_conflict="person_key")


@router.get("/pix-payments")
def listar_pix_payments(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    status: str | None = None,
    senderKey: str | None = None,
    conversationId: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status
    if senderKey:
        filters["sender_key"] = senderKey
    if conversationId:
        filters["conversation_id"] = conversationId
    return pix_payments_service.listar(usuario, page=page, page_size=pageSize, filters=filters)


@router.post("/pix-payments")
def criar_pix_payment(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return pix_payments_service.criar(usuario, body.to_db())


@router.get("/pix-payments/{record_id}")
def obter_pix_payment(record_id: int, usuario: dict = Depends(obter_usuario_atual)):
    return pix_payments_service.obter(usuario, record_id)


@router.patch("/pix-payments/{record_id}")
def atualizar_pix_payment(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return pix_payments_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))
