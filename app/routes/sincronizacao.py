from fastapi import APIRouter, Depends

from app.core.permissions import requer_permissao
from app.services.sincronizacao_service import SincronizacaoService

router = APIRouter()

sincronizacao = SincronizacaoService()


@router.post("/sincronizar")
def sincronizar(
    _: dict = Depends(requer_permissao("manageIntegrations")),
):
    return sincronizacao.sincronizar_tudo()