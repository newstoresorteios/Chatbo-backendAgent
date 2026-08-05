from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.auth import obter_usuario_atual
from app.services.commercial_bi_service import commercial_bi_service
from app.services.workspace_service import WORKSPACE_ADMIN_ROLES, workspace_service

router = APIRouter()


class AnalyzeRequest(BaseModel):
    periodDays: int = Field(default=30, ge=1, le=365)


@router.get("/commercial-bi/latest")
def latest_bi(usuario: dict = Depends(obter_usuario_atual)):
    context = workspace_service.get_current_workspace_context(usuario)
    latest = commercial_bi_service.latest_public(context["workspaceId"])
    return {"item": latest}


@router.post("/commercial-bi/analyze")
def analyze_bi(body: AnalyzeRequest | None = None, usuario: dict = Depends(obter_usuario_atual)):
    context = workspace_service.get_current_workspace_context(usuario)
    if context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES and context.get("accountType") != "system_admin":
        raise HTTPException(status_code=403, detail="Sem permissão para rodar análise BI.")
    period = int((body.periodDays if body else 30) or 30)
    try:
        return commercial_bi_service.analyze(
            context["workspaceId"],
            user_id=str(usuario.get("id")) if usuario.get("id") else None,
            period_days=period,
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
