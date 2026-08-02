from fastapi import APIRouter, Depends

from app.core.auth import obter_usuario_atual
from app.schemas.billing import PlanCreateRequest, PlanUpdateRequest, SelectPlanRequest
from app.services.billing_service import billing_service
from app.services.workspace_service import WORKSPACE_ADMIN_ROLES, WORKSPACE_VIEW_ROLES, workspace_service
from app.core.billing_permissions import requer_system_admin

router = APIRouter()


def _context(usuario: dict) -> dict:
    return workspace_service.get_current_workspace_context(usuario)


def _require_view(usuario: dict) -> dict:
    context = _context(usuario)
    if context.get("workspaceRole") not in WORKSPACE_VIEW_ROLES:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Você não possui permissão para visualizar o billing.")
    return context


def _require_admin(usuario: dict) -> dict:
    context = _context(usuario)
    if context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES:
        from fastapi import HTTPException
        raise HTTPException(status_code=403, detail="Apenas owner ou admin podem alterar o billing.")
    return context


@router.get("/billing/plans")
def listar_planos():
    return {"items": billing_service.listar_planos_publicos()}


@router.get("/billing/subscription")
def obter_assinatura(usuario: dict = Depends(obter_usuario_atual)):
    context = _require_view(usuario)
    return billing_service.assinatura(context["workspaceId"])


@router.get("/billing/overview")
def obter_overview(usuario: dict = Depends(obter_usuario_atual)):
    context = _require_view(usuario)
    return billing_service.overview(context["workspaceId"])


@router.post("/billing/select-plan")
def selecionar_plano(body: SelectPlanRequest, usuario: dict = Depends(obter_usuario_atual)):
    context = _require_admin(usuario)
    return billing_service.selecionar_plano(context["workspaceId"], body.planCode, body.billingInterval, str(usuario.get("id")))


@router.post("/billing/cancel")
def cancelar_assinatura(usuario: dict = Depends(obter_usuario_atual)):
    context = _require_admin(usuario)
    return billing_service.cancelar(context["workspaceId"], str(usuario.get("id")))


@router.post("/billing/reactivate")
def reativar_assinatura(usuario: dict = Depends(obter_usuario_atual)):
    context = _require_admin(usuario)
    return billing_service.reativar(context["workspaceId"], str(usuario.get("id")))


@router.get("/system/billing/plans")
def admin_listar_planos(usuario: dict = Depends(requer_system_admin)):
    return {"items": billing_service.admin_listar_planos(str(usuario.get("id")))}


@router.post("/system/billing/plans")
def admin_criar_plano(body: PlanCreateRequest, usuario: dict = Depends(requer_system_admin)):
    return billing_service.admin_criar_plano(str(usuario.get("id")), body)


@router.patch("/system/billing/plans/{plan_id}")
def admin_atualizar_plano(plan_id: str, body: PlanUpdateRequest, usuario: dict = Depends(requer_system_admin)):
    return billing_service.admin_atualizar_plano(str(usuario.get("id")), plan_id, body)


@router.get("/system/billing/subscriptions")
def admin_listar_assinaturas(usuario: dict = Depends(requer_system_admin)):
    return {"items": billing_service.admin_listar_assinaturas(str(usuario.get("id")))}


@router.get("/system/billing/subscriptions/{subscription_id}")
def admin_obter_assinatura(subscription_id: str, usuario: dict = Depends(requer_system_admin)):
    return billing_service.admin_obter_assinatura(str(usuario.get("id")), subscription_id)


@router.post("/system/billing/subscriptions/{subscription_id}/suspend")
def admin_suspender_assinatura(subscription_id: str, usuario: dict = Depends(requer_system_admin)):
    return billing_service.admin_suspender(str(usuario.get("id")), subscription_id)


@router.post("/system/billing/subscriptions/{subscription_id}/reactivate")
def admin_reativar_assinatura(subscription_id: str, usuario: dict = Depends(requer_system_admin)):
    return billing_service.admin_reativar(str(usuario.get("id")), subscription_id)
