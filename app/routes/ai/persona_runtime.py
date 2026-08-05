from __future__ import annotations

from datetime import datetime
from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.auth import obter_usuario_atual
from app.core.permissions import requer_permissao
from app.schemas.ai.common import FlexibleModel
from app.services.ai.resources import (
    instruction_extensions_service,
    persona_versions_service,
    prompt_compilations_service,
)

router = APIRouter()


@router.get("/persona-versions")
def listar_persona_versions(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    tenantId: str | None = None,
    personaKey: str | None = None,
    status: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if tenantId:
        filters["tenant_id"] = tenantId
    if personaKey:
        filters["persona_key"] = personaKey
    if status:
        filters["status"] = status
    return persona_versions_service.listar(usuario, page=page, page_size=pageSize, filters=filters)


@router.post("/persona-versions")
def criar_persona_version(
    body: FlexibleModel,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    return persona_versions_service.criar(usuario, body.to_db())


@router.patch("/persona-versions/{record_id}")
def atualizar_persona_version(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    payload = body.to_db(exclude_none=True)
    status = payload.get("status")
    if status == "active" and "activated_at" not in payload:
        payload["activated_at"] = datetime.utcnow().isoformat()
    if status == "archived" and "archived_at" not in payload:
        payload["archived_at"] = datetime.utcnow().isoformat()
    return persona_versions_service.atualizar(usuario, record_id, payload)


@router.get("/instruction-extensions")
def listar_instruction_extensions(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    tenantId: str | None = None,
    scope: str | None = None,
    status: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if tenantId:
        filters["tenant_id"] = tenantId
    if scope:
        filters["scope"] = scope
    if status:
        filters["status"] = status
    return instruction_extensions_service.listar(
        usuario, page=page, page_size=pageSize, filters=filters
    )


@router.post("/instruction-extensions")
def criar_instruction_extension(
    body: FlexibleModel,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    return instruction_extensions_service.criar(usuario, body.to_db())


@router.patch("/instruction-extensions/{record_id}")
def atualizar_instruction_extension(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    return instruction_extensions_service.atualizar(
        usuario, record_id, body.to_db(exclude_none=True)
    )


@router.get("/prompt-compilations")
def listar_prompt_compilations(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    tenantId: str | None = None,
    conversationKey: str | None = None,
    senderKey: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if tenantId:
        filters["tenant_id"] = tenantId
    if conversationKey:
        filters["conversation_key"] = conversationKey
    if senderKey:
        filters["sender_key"] = senderKey
    return prompt_compilations_service.listar(
        usuario, page=page, page_size=pageSize, filters=filters
    )


@router.post("/prompt-compilations")
def criar_prompt_compilation(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return prompt_compilations_service.criar(usuario, body.to_db())
