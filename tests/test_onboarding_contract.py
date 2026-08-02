import unittest
from unittest.mock import Mock

from fastapi import HTTPException

from app.services.workspace_service import WorkspaceService


class FakeWorkspaceRepository:
    def __init__(self):
        self.workspace = {"id": "ws-1", "name": "Empresa Real", "brand_name": None, "status": "active"}
        self.settings = {}
        self.onboarding = {"workspace_id": "ws-1", "status": "pending", "current_step": "empresa", "completed_steps": []}
        self.channels = []
        self.tests = []
        self.saved_products = False

    def buscar_membership_ativo(self, user_id):
        return {"workspace_id": "ws-1", "role": "owner", "workspaces": self.workspace}

    def buscar_workspace(self, workspace_id):
        return self.workspace

    def obter_onboarding(self, workspace_id):
        return self.onboarding

    def obter_settings(self, workspace_id):
        return self.settings

    def listar_canais(self, workspace_id):
        return self.channels

    def ultimo_teste_sucesso(self, workspace_id, persona_id):
        return next((row for row in self.tests if row["status"] == "success" and row["persona_id"] == persona_id), None)

    def salvar_onboarding(self, workspace_id, data):
        self.onboarding.update(data)
        return self.onboarding

    def salvar_canal(self, workspace_id, channel_type, payload):
        row = {"id": f"channel-{channel_type}", "workspace_id": workspace_id, "channel_type": channel_type, **payload}
        self.channels = [item for item in self.channels if item["channel_type"] != channel_type] + [row]
        return row

    def registrar_onboarding_test(self, payload):
        self.tests.append(payload)
        return payload


class FakePersonaRepository:
    def __init__(self):
        self.personas = []

    def listar_por_workspace(self, workspace_id):
        return self.personas

    def buscar_ativa(self, workspace_id):
        return next((row for row in self.personas if row["status"] == "active"), None)


class FakeCatalogRepository:
    def __init__(self, count=0):
        self.count = count
        self.write_called = False

    def contar_produtos(self):
        return self.count


class OnboardingContractTest(unittest.TestCase):
    def setUp(self):
        self.service = WorkspaceService()
        self.service.repo = FakeWorkspaceRepository()
        self.service.persona_repo = FakePersonaRepository()
        self.service.catalog_repo = FakeCatalogRepository()
        self.service.settings_repo = Mock(obter_empresa=Mock(return_value={}))
        self.user = {"id": "user-1"}

    def configure_company_operation(self):
        self.service.repo.settings.update({
            "country": "BR", "currency": "BRL", "segment": "distribuicao",
            "sales_model": "b2b", "sales_channels": ["representantes"],
            "business_hours": "09:00-18:00", "primary_contact": "owner@example.com",
        })

    def activate_persona(self, persona_id="persona-1"):
        self.service.persona_repo.personas.append({"id": persona_id, "workspace_id": "ws-1", "status": "active"})

    def test_initial_state_and_company_operation_requirements(self):
        state = self.service.obter_onboarding(self.user)
        self.assertEqual(state["status"], "pending")
        self.assertEqual(state["currentStep"], "empresa")
        self.assertFalse(state["requirements"]["companyConfigured"])
        self.configure_company_operation()
        requirements = self.service.obter_onboarding(self.user)["requirements"]
        self.assertTrue(requirements["companyConfigured"])
        self.assertTrue(requirements["operationConfigured"])

    def test_legacy_catalog_is_available_without_writing_products(self):
        self.service.catalog_repo.count = 3
        catalog = self.service.obter_onboarding(self.user)["requirements"]
        self.assertTrue(catalog["catalogAvailable"])
        self.assertEqual(catalog["catalogScope"], "legacy_global")
        self.assertFalse(self.service.catalog_repo.write_called)

    def test_draft_persona_and_missing_requirements_block_activation(self):
        self.configure_company_operation()
        self.service.catalog_repo.count = 1
        self.service.persona_repo.personas.append({"id": "persona-1", "workspace_id": "ws-1", "status": "draft"})
        with self.assertRaises(HTTPException) as error:
            self.service.ativar_onboarding(self.user)
        self.assertEqual(error.exception.status_code, 409)
        self.assertIn("channelConfigured", error.exception.detail["missingRequirements"])
        self.assertFalse(self.service.obter_onboarding(self.user)["requirements"]["personaActive"])

    def test_active_persona_requires_test_for_same_persona(self):
        self.configure_company_operation()
        self.service.catalog_repo.count = 1
        self.activate_persona()
        self.service.repo.salvar_canal("ws-1", "webchat", {"status": "configured", "configuration": {}})
        requirements = self.service.obter_onboarding(self.user)["requirements"]
        self.assertTrue(requirements["personaActive"])
        self.assertFalse(requirements["testCompleted"])
        self.service.repo.tests.append({"status": "success", "persona_id": "persona-old"})
        self.assertFalse(self.service.obter_onboarding(self.user)["requirements"]["testCompleted"])

    def test_activation_completes_only_when_all_requirements_are_real(self):
        self.configure_company_operation()
        self.service.catalog_repo.count = 1
        self.activate_persona()
        self.service.repo.salvar_canal("ws-1", "webchat", {"status": "configured", "configuration": {}})
        self.service.repo.tests.append({"status": "success", "persona_id": "persona-1"})
        result = self.service.ativar_onboarding(self.user)
        self.assertEqual(result["status"], "complete")
        self.assertEqual(result["completedSteps"], ["empresa", "operacao", "catalogo", "canais", "persona", "teste", "ativacao"])

    def test_supervisor_can_read_but_not_change(self):
        self.service.get_current_workspace_context = Mock(return_value={"workspaceId": "ws-1", "workspaceRole": "supervisor"})
        self.assertEqual(self.service.obter_onboarding(self.user)["status"], "pending")
        with self.assertRaises(HTTPException) as error:
            self.service.salvar_canal(self.user, {"channelType": "webchat"})
        self.assertEqual(error.exception.status_code, 403)


if __name__ == "__main__":
    unittest.main()
