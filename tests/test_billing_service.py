import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from app.services.billing_provider import NoopBillingProvider
from app.services.billing_service import BillingService


def plan(code="starter", public=True):
    return {
        "id": f"plan-{code}", "code": code, "name": code.title(), "description": None,
        "status": "active", "billing_interval": "monthly", "price_cents": 0,
        "pricing_mode": "contact_sales", "currency": "BRL", "trial_days": 14 if code != "enterprise" else 0,
        "limits": {"users": 3, "aiMessagesPerMonth": 1000}, "features": {"webchat": True},
        "sort_order": 1, "is_public": public,
    }


class FakeBillingRepository:
    def __init__(self):
        self.plans = {"starter": plan(), "professional": plan("professional"), "enterprise": plan("enterprise", False)}
        self.subscriptions = []
        self.events = []
        self.usage = []
        self.next_id = 1

    def listar_planos_publicos(self):
        return [row for row in self.plans.values() if row["status"] == "active" and row["is_public"]]

    def listar_planos(self):
        return list(self.plans.values())

    def buscar_plano(self, plan_id):
        return next((row for row in self.plans.values() if row["id"] == plan_id), None)

    def buscar_plano_por_code(self, code):
        return self.plans.get(code)

    def assinatura_corrente(self, workspace_id):
        return next((row for row in reversed(self.subscriptions) if row["workspace_id"] == workspace_id and row["status"] in {"trialing", "active", "past_due", "suspended"}), None)

    def assinatura_por_id(self, subscription_id):
        return next((row for row in self.subscriptions if row["id"] == subscription_id), None)

    def listar_assinaturas(self):
        return self.subscriptions

    def criar_assinatura(self, payload):
        row = {"id": f"subscription-{self.next_id}", **payload}
        self.next_id += 1
        self.subscriptions.append(row)
        return row

    def atualizar_assinatura(self, subscription_id, payload):
        row = self.assinatura_por_id(subscription_id)
        row.update(payload)
        return row

    def registrar_evento(self, payload):
        self.events.append(payload)
        return payload

    def uso_periodo(self, workspace_id, period_key):
        return [row for row in self.usage if row["workspace_id"] == workspace_id and row["period_key"] == period_key]


class BillingServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo = FakeBillingRepository()
        self.service = BillingService(repo=self.repo)
        self.service.users_repo = Mock()
        self.service.users_repo.buscar_por_id.return_value = {"id": "system-1", "account_type": "system_admin"}

    def test_public_plans_exclude_private_plan(self):
        result = self.service.listar_planos_publicos()
        self.assertEqual([item["code"] for item in result], ["starter", "professional"])

    def test_trial_is_created_and_event_recorded(self):
        created = self.service.criar_trial("workspace-1", "user-1")
        self.assertEqual(created["status"], "trialing")
        self.assertEqual(len(self.repo.events), 1)
        self.assertEqual(self.repo.events[0]["event_type"], "trial_started")

    def test_overview_contains_entitlements_and_usage(self):
        self.service.criar_trial("workspace-1", "user-1")
        self.repo.usage.append({"workspace_id": "workspace-1", "metric": "ai_messages", "period_key": self.service._period_key(), "used_value": 7})
        overview = self.service.overview("workspace-1")
        self.assertEqual(overview["subscriptionState"], "trialing")
        self.assertTrue(overview["entitlements"]["features"]["webchat"])
        self.assertEqual(overview["entitlements"]["usage"]["values"]["ai_messages"], 7)

    def test_feature_and_limit_entitlements_are_centralized(self):
        self.service.criar_trial("workspace-1", "user-1")
        self.assertTrue(self.service.feature_enabled("workspace-1", "webchat"))
        self.assertEqual(self.service.limit_for("workspace-1", "users"), 3)
        self.assertEqual(self.service.limit_for("workspace-1", "unknown"), None)

    def test_usage_below_at_and_above_limit(self):
        self.service.criar_trial("workspace-1", "user-1")
        metric = {"workspace_id": "workspace-1", "metric": "ai_messages", "period_key": self.service._period_key(), "used_value": 999}
        self.repo.usage.append(metric)
        self.assertTrue(self.service.action_allowed("workspace-1", metric="ai_messages", increment=1))
        metric["used_value"] = 1000
        self.assertFalse(self.service.action_allowed("workspace-1", metric="ai_messages", increment=1))
        metric["used_value"] = 1001
        self.assertFalse(self.service.action_allowed("workspace-1", metric="ai_messages", increment=0))

    def test_legacy_workspace_is_unassigned_without_backfill(self):
        result = self.service.assinatura("legacy-workspace")
        self.assertEqual(result["subscriptionState"], "legacy_unassigned")
        self.assertEqual(self.repo.subscriptions, [])

    def test_private_plan_cannot_be_selected(self):
        with self.assertRaises(HTTPException) as error:
            self.service.selecionar_plano("workspace-1", "enterprise", "monthly", "user-1")
        self.assertEqual(error.exception.status_code, 404)

    def test_select_cancel_and_reactivate_during_trial(self):
        self.service.criar_trial("workspace-1", "user-1")
        selected = self.service.selecionar_plano("workspace-1", "professional", "monthly", "user-1")
        self.assertEqual(selected["planCode"], "professional")
        canceled = self.service.cancelar("workspace-1", "user-1")
        self.assertTrue(canceled["cancelAtPeriodEnd"])
        reactivated = self.service.reativar("workspace-1", "user-1")
        self.assertFalse(reactivated["cancelAtPeriodEnd"])
        self.assertIn("cancellation_requested", [event["event_type"] for event in self.repo.events])

    def test_noop_provider_never_approves_checkout(self):
        with self.assertRaises(RuntimeError):
            NoopBillingProvider().create_checkout({})

    def test_global_admin_validation_is_separate_from_workspace_role(self):
        self.service.users_repo.buscar_por_id.return_value = {"id": "user-1", "account_type": "workspace_user"}
        with self.assertRaises(HTTPException) as error:
            self.service.admin_listar_planos("user-1")
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
