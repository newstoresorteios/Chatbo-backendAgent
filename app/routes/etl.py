from fastapi import APIRouter, HTTPException, Query

from app.config.settings import ETL_CRON_SECRET
from app.services.etl_service import etl_service

router = APIRouter()


def _validar_token(token: str | None) -> None:
    segredo = (ETL_CRON_SECRET or "").strip()
    if not segredo:
        raise HTTPException(
            status_code=503,
            detail="ETL_CRON_SECRET não configurado no Render.",
        )
    if (token or "").strip() != segredo:
        raise HTTPException(status_code=403, detail="Token ETL inválido.")


@router.post("/etl/run")
@router.get("/etl/run")
def executar_etl(
    job: str = Query("orders", description="orders (30min) | catalog (diário) | full"),
    token: str = Query(..., description="ETL_CRON_SECRET"),
):
    """
    ETL agendado (Render Cron). Extrai Mercos → Supabase com pausas e rate-limit.
    O agente de vendas lê apenas o Supabase — não martela a API Mercos.
    """
    _validar_token(token)
    try:
        return etl_service.executar(job)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=502, detail=f"Falha no ETL: {exc}") from exc
