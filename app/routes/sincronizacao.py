from fastapi import APIRouter, Depends

from app.core.permissions import requer_permissao
from app.core.workspace_scope import obter_company_context, workspace_id_from_context
from app.services.sincronizacao_service import SincronizacaoService

router = APIRouter()

sincronizacao = SincronizacaoService()


@router.post("/sincronizar")
def sincronizar(
    _: dict = Depends(requer_permissao("manageIntegrations")),
    context: dict = Depends(obter_company_context),
):
    return sincronizacao.sincronizar_tudo(
        workspace_id=workspace_id_from_context(context),
    )
