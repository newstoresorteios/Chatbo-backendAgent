from fastapi import APIRouter, Depends, HTTPException

from app.core.auth import verificar_token
from app.core.permissions import requer_permissao
from app.services.pulsedesk_adapter import (
    dashboard_data,
    listar_clientes,
    listar_produtos,
    listar_pedidos,
    obter_cliente,
)
from app.services.vendas_service import vendas_service
from app.services.rankings_service import rankings_service

router = APIRouter()


@router.get("/dashboard")
def get_dashboard(autorizado=Depends(verificar_token)):
    return dashboard_data()


@router.get("/vendas/metricas")
def get_vendas_metricas(_: dict = Depends(requer_permissao("viewReports"))):
    return vendas_service.metricas()


@router.get("/vendas/rankings")
def get_vendas_rankings(
    limit: int = 10,
    _: dict = Depends(requer_permissao("viewReports")),
):
    return rankings_service.rankings(limit=limit)


@router.get("/clientes")
def get_clientes(
    page: int = 1,
    pageSize: int = 10,
    search: str = "",
    autorizado=Depends(verificar_token),
):
    return listar_clientes(page=page, page_size=pageSize, search=search)


@router.get("/clientes/{cliente_id}")
def get_cliente(cliente_id: str, autorizado=Depends(verificar_token)):
    cliente = obter_cliente(cliente_id)
    if not cliente:
        raise HTTPException(status_code=404, detail="Cliente não encontrado")
    return cliente


@router.get("/produtos")
def get_produtos(
    page: int = 1,
    pageSize: int = 10,
    search: str = "",
    category: str | None = None,
    autorizado=Depends(verificar_token),
):
    return listar_produtos(page=page, page_size=pageSize, search=search, category=category)


@router.get("/pedidos")
def get_pedidos(
    page: int = 1,
    pageSize: int = 10,
    search: str = "",
    status: str | None = None,
    autorizado=Depends(verificar_token),
):
    return listar_pedidos(page=page, page_size=pageSize, search=search, status=status)
