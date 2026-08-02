from fastapi import APIRouter, Depends

from app.core.auth import verificar_token
from app.services.dashboard_service import DashboardService

router = APIRouter()

dashboard = DashboardService()


@router.get("/resumo")
def resumo(
    autorizado=Depends(verificar_token)
):
    return dashboard.resumo()