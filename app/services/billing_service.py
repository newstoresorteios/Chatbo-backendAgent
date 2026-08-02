from datetime import datetime, timedelta
from typing import Any

from fastapi import HTTPException

from app.repositories.billing_repository import BillingRepository
from app.repositories.usuario_repository import UsuarioRepository
from app.schemas.billing import PlanCreateRequest, PlanUpdateRequest
from app.services.billing_provider import BillingProvider, NoopBillingProvider

BILLING_CURRENT_STATUSES = {"trialing", "active", "past_due", "suspended"}
PLAN_STATUSES = {"active", "inactive", "archived"}
BILLING_INTERVALS = {"monthly", "yearly"}
ENTITLEMENT_METRICS = {"users", "conversations", "ai_messages", "active_personas", "channels", "products", "storage_bytes"}


class BillingService:
    def __init__(self, repo: BillingRepository | None = None, provider: BillingProvider | None = None):
        self.repo = repo or BillingRepository()
        self.provider = provider or NoopBillingProvider()
        self.users_repo = UsuarioRepository()

    def _now(self) -> datetime:
        return datetime.utcnow()

    def _period_key(self, now: datetime | None = None) -> str:
        current = now or self._now()
        return f"{current.year:04d}-{current.month:02d}"

    def _clean_dict(self, value: Any) -> dict:
        return value if isinstance(value, dict) else {}

    def _plan_response(self, row: dict, detail: bool = False) -> dict:
        response = {
            "id": str(row.get("id")), "code": row.get("code"), "name": row.get("name"),
            "description": row.get("description"), "status": row.get("status"),
            "billingInterval": row.get("billing_interval"), "priceCents": int(row.get("price_cents") or 0),
            "pricingMode": row.get("pricing_mode") or "contact_sales", "currency": row.get("currency") or "BRL",
            "trialDays": int(row.get("trial_days") or 0), "sortOrder": int(row.get("sort_order") or 0),
            "isPublic": bool(row.get("is_public")),
        }
        if detail:
            response["limits"] = self._clean_dict(row.get("limits"))
            response["features"] = self._clean_dict(row.get("features"))
        return response

    def _effective_status(self, subscription: dict) -> str:
        status = subscription.get("status")
        now = self._now()
        if status == "trialing" and subscription.get("trial_ends_at"):
            try:
                if now > datetime.fromisoformat(str(subscription["trial_ends_at"]).replace("Z", "+00:00")).replace(tzinfo=None):
                    return "expired"
            except ValueError:
                pass
        if status == "canceled" and subscription.get("current_period_ends_at"):
            try:
                if now > datetime.fromisoformat(str(subscription["current_period_ends_at"]).replace("Z", "+00:00")).replace(tzinfo=None):
                    return "expired"
            except ValueError:
                pass
        return status or "legacy_unassigned"

    def _subscription_response(self, row: dict, plan: dict) -> dict:
        return {
            "id": str(row.get("id")), "workspaceId": str(row.get("workspace_id")),
            "status": row.get("status"), "effectiveStatus": self._effective_status(row),
            "planCode": plan.get("code"), "planName": plan.get("name"),
            "billingInterval": row.get("billing_interval"), "currency": row.get("currency"),
            "unitAmountCents": int(row.get("unit_amount_cents") or 0),
            "trialStartedAt": row.get("trial_started_at"), "trialEndsAt": row.get("trial_ends_at"),
            "currentPeriodStartedAt": row.get("current_period_started_at"),
            "currentPeriodEndsAt": row.get("current_period_ends_at"),
            "cancelAtPeriodEnd": bool(row.get("cancel_at_period_end")),
        }

    def _event(self, workspace_id: str, subscription_id: str | None, event_type: str, previous: str | None, new: str | None, created_by: str | None, payload: dict | None = None) -> None:
        self.repo.registrar_evento({
            "workspace_id": workspace_id, "subscription_id": subscription_id, "event_type": event_type,
            "previous_status": previous, "new_status": new, "payload": payload or {}, "created_by": created_by,
        })

    def _validate_interval(self, interval: str) -> None:
        if interval not in BILLING_INTERVALS:
            raise HTTPException(status_code=422, detail="Intervalo de cobrança inválido.")

    def criar_trial(self, workspace_id: str, created_by: str | None = None) -> dict | None:
        if self.repo.assinatura_corrente(workspace_id):
            return None
        plan = self.repo.buscar_plano_por_code("starter")
        if not plan or plan.get("status") != "active":
            return None
        started = self._now()
        trial_days = int(plan.get("trial_days") or 0)
        ends = started + timedelta(days=trial_days) if trial_days else None
        subscription = self.repo.criar_assinatura({
            "workspace_id": workspace_id, "plan_id": plan["id"], "status": "trialing" if ends else "active",
            "billing_interval": plan.get("billing_interval") or "monthly", "currency": plan.get("currency") or "BRL",
            "unit_amount_cents": int(plan.get("price_cents") or 0), "trial_started_at": started.isoformat(),
            "trial_ends_at": ends.isoformat() if ends else None, "metadata": {"source": "workspace_registration"},
        })
        self._event(workspace_id, str(subscription.get("id")), "trial_started", None, subscription.get("status"), created_by, {"planCode": plan.get("code")})
        return subscription

    def listar_planos_publicos(self) -> list[dict]:
        return [self._plan_response(row) for row in self.repo.listar_planos_publicos()]

    def _subscription_and_plan(self, workspace_id: str) -> tuple[dict | None, dict | None]:
        subscription = self.repo.assinatura_corrente(workspace_id)
        if not subscription:
            return None, None
        plan = self.repo.buscar_plano(str(subscription.get("plan_id")))
        return subscription, plan

    def assinatura(self, workspace_id: str) -> dict:
        subscription, plan = self._subscription_and_plan(workspace_id)
        if not subscription or not plan:
            return {"subscription": None, "subscriptionState": "legacy_unassigned"}
        return self._subscription_response(subscription, plan)

    def _usage(self, workspace_id: str) -> dict:
        period = self._period_key()
        values = {row.get("metric"): int(row.get("used_value") or 0) for row in self.repo.uso_periodo(workspace_id, period) if row.get("metric")}
        return {"values": values, "periodKey": period}

    def _plan_entitlements(self, workspace_id: str) -> tuple[dict | None, dict | None, dict]:
        subscription, plan = self._subscription_and_plan(workspace_id)
        return subscription, plan, self._usage(workspace_id)

    def feature_enabled(self, workspace_id: str, feature: str) -> bool:
        _, plan, _ = self._plan_entitlements(workspace_id)
        return bool(plan and self._clean_dict(plan.get("features")).get(feature) is True)

    def limit_for(self, workspace_id: str, limit_name: str) -> int | None:
        _, plan, _ = self._plan_entitlements(workspace_id)
        if not plan:
            return None
        value = self._clean_dict(plan.get("limits")).get(limit_name)
        return int(value) if isinstance(value, (int, float)) and not isinstance(value, bool) else None

    def usage_for(self, workspace_id: str, metric: str) -> int:
        _, _, usage = self._plan_entitlements(workspace_id)
        return int(usage["values"].get(metric) or 0)

    def consume_usage(self, workspace_id: str, metric: str, amount: int = 1) -> dict:
        if metric not in ENTITLEMENT_METRICS or amount < 1:
            raise HTTPException(status_code=422, detail="Métrica de uso inválida.")
        if not self.action_allowed(workspace_id, metric=metric, increment=amount):
            raise HTTPException(status_code=409, detail={"code": "PLAN_LIMIT_REACHED", "metric": metric})
        period_key = self._period_key()
        current = self.usage_for(workspace_id, metric)
        updated = self.repo.registrar_uso(workspace_id, metric, period_key, current + amount)
        return {"metric": metric, "periodKey": period_key, "used": int(updated.get("used_value") or current + amount), "limit": self.limit_for(workspace_id, metric)}

    def action_allowed(self, workspace_id: str, *, feature: str | None = None, metric: str | None = None, increment: int = 1) -> bool:
        subscription, plan, usage = self._plan_entitlements(workspace_id)
        if not subscription or not plan or self._effective_status(subscription) in {"expired", "canceled", "suspended"}:
            return False
        if feature and not self.feature_enabled(workspace_id, feature):
            return False
        if metric:
            limit_key = {"ai_messages": "aiMessagesPerMonth", "conversations": "conversationsPerMonth"}.get(metric, metric)
            value = self._clean_dict(plan.get("limits")).get(limit_key)
            if isinstance(value, (int, float)) and not isinstance(value, bool) and int(usage["values"].get(metric) or 0) + increment > int(value):
                return False
        return True

    def overview(self, workspace_id: str) -> dict:
        subscription, plan = self._subscription_and_plan(workspace_id)
        usage = self._usage(workspace_id)
        if not subscription or not plan:
            return {"subscription": None, "subscriptionState": "legacy_unassigned", "plan": None, "entitlements": {"features": {}, "limits": {}, "usage": usage}}
        return {
            "subscription": self._subscription_response(subscription, plan),
            "subscriptionState": self._effective_status(subscription),
            "plan": self._plan_response(plan, detail=True),
            "entitlements": {"features": self._clean_dict(plan.get("features")), "limits": self._clean_dict(plan.get("limits")), "usage": usage},
        }

    def selecionar_plano(self, workspace_id: str, plan_code: str, billing_interval: str, created_by: str) -> dict:
        self._validate_interval(billing_interval)
        plan = self.repo.buscar_plano_por_code(plan_code)
        if not plan or plan.get("status") != "active" or not plan.get("is_public"):
            raise HTTPException(status_code=404, detail="Plano público ativo não encontrado.")
        subscription, current_plan = self._subscription_and_plan(workspace_id)
        if subscription and (subscription.get("provider") or subscription.get("provider_subscription_id")):
            raise HTTPException(status_code=409, detail={"message": "Este plano exige checkout.", "checkoutRequired": True})
        if subscription:
            previous = subscription.get("status")
            updated = self.repo.atualizar_assinatura(str(subscription["id"]), {
                "plan_id": plan["id"], "billing_interval": billing_interval, "currency": plan.get("currency") or "BRL",
                "unit_amount_cents": int(plan.get("price_cents") or 0), "cancel_at_period_end": False, "canceled_at": None,
            })
            self._event(workspace_id, str(subscription["id"]), "plan_changed", previous, updated.get("status") or previous, created_by, {"fromPlanCode": current_plan.get("code") if current_plan else None, "toPlanCode": plan.get("code")})
            return self._subscription_response(updated, plan)
        now = self._now()
        trial_days = int(plan.get("trial_days") or 0)
        ends = now + timedelta(days=trial_days) if trial_days else None
        created = self.repo.criar_assinatura({
            "workspace_id": workspace_id, "plan_id": plan["id"], "status": "trialing" if ends else "active",
            "billing_interval": billing_interval, "currency": plan.get("currency") or "BRL", "unit_amount_cents": int(plan.get("price_cents") or 0),
            "trial_started_at": now.isoformat() if ends else None, "trial_ends_at": ends.isoformat() if ends else None,
            "metadata": {"source": "plan_selection"},
        })
        event = "trial_started" if ends else "subscription_created"
        self._event(workspace_id, str(created.get("id")), event, None, created.get("status"), created_by, {"planCode": plan.get("code")})
        return self._subscription_response(created, plan)

    def cancelar(self, workspace_id: str, created_by: str) -> dict:
        subscription, plan = self._subscription_and_plan(workspace_id)
        if not subscription or not plan:
            raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
        effective = self._effective_status(subscription)
        if effective in {"expired", "canceled"}:
            raise HTTPException(status_code=409, detail="Esta assinatura não pode ser cancelada novamente.")
        updated = self.repo.atualizar_assinatura(str(subscription["id"]), {"cancel_at_period_end": True, "canceled_at": self._now().isoformat()})
        self._event(workspace_id, str(subscription["id"]), "cancellation_requested", subscription.get("status"), updated.get("status"), created_by)
        return self._subscription_response(updated, plan)

    def reativar(self, workspace_id: str, created_by: str) -> dict:
        subscription, plan = self._subscription_and_plan(workspace_id)
        if not subscription or not plan:
            raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
        if self._effective_status(subscription) in {"expired", "canceled", "suspended"}:
            raise HTTPException(status_code=409, detail="Esta assinatura não pode ser reativada localmente.")
        updated = self.repo.atualizar_assinatura(str(subscription["id"]), {"cancel_at_period_end": False, "canceled_at": None, "suspended_at": None})
        self._event(workspace_id, str(subscription["id"]), "subscription_reactivated", subscription.get("status"), updated.get("status"), created_by)
        return self._subscription_response(updated, plan)

    def _admin_user(self, user_id: str) -> None:
        user = self.users_repo.buscar_por_id(user_id)
        if not user or user.get("account_type") != "system_admin":
            raise HTTPException(status_code=403, detail="Apenas administradores globais podem executar esta ação.")

    def _plan_payload(self, body: PlanCreateRequest | PlanUpdateRequest, partial: bool = False) -> dict:
        raw = body.model_dump(exclude_unset=partial)
        mapping = {"billingInterval": "billing_interval", "priceCents": "price_cents", "pricingMode": "pricing_mode", "trialDays": "trial_days", "sortOrder": "sort_order", "isPublic": "is_public"}
        return {mapping.get(key, key): value for key, value in raw.items()}

    def admin_listar_planos(self, user_id: str) -> list[dict]:
        self._admin_user(user_id)
        return [self._plan_response(row, detail=True) for row in self.repo.listar_planos()]

    def admin_criar_plano(self, user_id: str, body: PlanCreateRequest) -> dict:
        self._admin_user(user_id)
        payload = self._plan_payload(body)
        if payload.get("status") not in PLAN_STATUSES or payload.get("billing_interval") not in BILLING_INTERVALS or payload.get("pricing_mode") not in {"fixed", "contact_sales"}:
            raise HTTPException(status_code=422, detail="Configuração de plano inválida.")
        return self._plan_response(self.repo.criar_plano(payload), detail=True)

    def admin_atualizar_plano(self, user_id: str, plan_id: str, body: PlanUpdateRequest) -> dict:
        self._admin_user(user_id)
        current = self.repo.buscar_plano(plan_id)
        if not current:
            raise HTTPException(status_code=404, detail="Plano não encontrado.")
        payload = self._plan_payload(body, partial=True)
        if payload.get("status") not in (None, *PLAN_STATUSES) or payload.get("billing_interval") not in (None, *BILLING_INTERVALS) or payload.get("pricing_mode") not in (None, "fixed", "contact_sales"):
            raise HTTPException(status_code=422, detail="Configuração de plano inválida.")
        return self._plan_response(self.repo.atualizar_plano(plan_id, payload), detail=True)

    def admin_listar_assinaturas(self, user_id: str) -> list[dict]:
        self._admin_user(user_id)
        result = []
        for row in self.repo.listar_assinaturas():
            plan = self.repo.buscar_plano(str(row.get("plan_id")))
            if plan:
                result.append(self._subscription_response(row, plan))
        return result

    def admin_obter_assinatura(self, user_id: str, subscription_id: str) -> dict:
        self._admin_user(user_id)
        row = self.repo.assinatura_por_id(subscription_id)
        plan = self.repo.buscar_plano(str(row.get("plan_id"))) if row else None
        if not row or not plan:
            raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
        return self._subscription_response(row, plan)

    def admin_suspender(self, user_id: str, subscription_id: str) -> dict:
        self._admin_user(user_id)
        row = self.repo.assinatura_por_id(subscription_id)
        plan = self.repo.buscar_plano(str(row.get("plan_id"))) if row else None
        if not row or not plan:
            raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
        updated = self.repo.atualizar_assinatura(subscription_id, {"status": "suspended", "suspended_at": self._now().isoformat()})
        self._event(str(row["workspace_id"]), subscription_id, "subscription_suspended", row.get("status"), "suspended", user_id)
        return self._subscription_response(updated, plan)

    def admin_reativar(self, user_id: str, subscription_id: str) -> dict:
        self._admin_user(user_id)
        row = self.repo.assinatura_por_id(subscription_id)
        plan = self.repo.buscar_plano(str(row.get("plan_id"))) if row else None
        if not row or not plan:
            raise HTTPException(status_code=404, detail="Assinatura não encontrada.")
        updated = self.repo.atualizar_assinatura(subscription_id, {"status": "active", "suspended_at": None, "cancel_at_period_end": False})
        self._event(str(row["workspace_id"]), subscription_id, "subscription_reactivated", row.get("status"), "active", user_id)
        return self._subscription_response(updated, plan)


billing_service = BillingService()
