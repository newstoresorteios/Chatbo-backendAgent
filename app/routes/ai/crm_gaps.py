from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query

from app.core.auth import obter_usuario_atual
from app.schemas.ai.common import FlexibleModel
from app.services.ai.resources import coupon_users_service, leads_service

router = APIRouter()


@router.get("/leads")
def listar_leads(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    status: str | None = None,
    search: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    filters: dict[str, Any] = {}
    if status:
        filters["status"] = status
    return leads_service.listar(
        usuario,
        page=page,
        page_size=pageSize,
        filters=filters,
        search_column="nome" if search else None,
        search=search,
    )


@router.post("/leads")
def criar_lead(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    return leads_service.criar(usuario, body.to_db())


@router.get("/leads/{record_id}")
def obter_lead(record_id: str, usuario: dict = Depends(obter_usuario_atual)):
    return leads_service.obter(usuario, record_id)


@router.patch("/leads/{record_id}")
def atualizar_lead(
    record_id: str,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    return leads_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))


@router.get("/coupon-users")
def listar_coupon_users(
    page: int = Query(1, ge=1),
    pageSize: int = Query(50, ge=1, le=200),
    search: str | None = None,
    usuario: dict = Depends(obter_usuario_atual),
):
    # Auth required; tabela users (cupom) é global (sem workspace_id).
    _ = usuario
    return coupon_users_service.listar(
        usuario,
        page=page,
        page_size=pageSize,
        search_column="email" if search else None,
        search=search,
    )


@router.post("/coupon-users")
def criar_coupon_user(body: FlexibleModel, usuario: dict = Depends(obter_usuario_atual)):
    _ = usuario
    return coupon_users_service.criar(usuario, body.to_db())


@router.get("/coupon-users/{record_id}")
def obter_coupon_user(record_id: int, usuario: dict = Depends(obter_usuario_atual)):
    _ = usuario
    return coupon_users_service.obter(usuario, record_id)


@router.patch("/coupon-users/{record_id}")
def atualizar_coupon_user(
    record_id: int,
    body: FlexibleModel,
    usuario: dict = Depends(obter_usuario_atual),
):
    _ = usuario
    return coupon_users_service.atualizar(usuario, record_id, body.to_db(exclude_none=True))
