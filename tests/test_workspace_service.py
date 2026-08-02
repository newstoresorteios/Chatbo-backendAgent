import unittest
import sys
import types
from unittest.mock import Mock

fastapi_stub = sys.modules.get("fastapi") or types.ModuleType("fastapi")


class HTTPException(Exception):
    def __init__(self, status_code: int, detail: str):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


fastapi_stub.HTTPException = getattr(fastapi_stub, "HTTPException", HTTPException)
HTTPException = fastapi_stub.HTTPException
sys.modules.setdefault("fastapi", fastapi_stub)

supabase_stub = types.ModuleType("supabase")
supabase_stub.Client = object
supabase_stub.create_client = lambda *_args, **_kwargs: object()
sys.modules.setdefault("supabase", supabase_stub)

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

from app.services.workspace_service import WorkspaceService


class WorkspaceServiceTest(unittest.TestCase):
    def test_context_uses_explicit_system_admin_only(self):
        service = WorkspaceService()
        service.repo = Mock()
        service.repo.buscar_membership_ativo.return_value = {
            "workspace_id": "workspace-1",
            "role": "admin",
            "workspaces": {"id": "workspace-1", "name": "NITRUS", "status": "active"},
        }
        service.repo.obter_onboarding.return_value = {"status": "complete"}

        context = service.get_current_workspace_context({
            "id": "user-1",
            "email": "admin@example.com",
            "perfil": "admin",
            "account_type": "workspace_user",
        })

        self.assertEqual(context["accountType"], "workspace_user")
        self.assertEqual(context["workspaceRole"], "admin")

    def test_context_preserves_explicit_system_admin(self):
        service = WorkspaceService()
        service.repo = Mock()
        service.repo.buscar_membership_ativo.return_value = {
            "workspace_id": "workspace-1",
            "role": "owner",
            "workspaces": {"id": "workspace-1", "name": "NITRUS", "status": "active"},
        }
        service.repo.obter_onboarding.return_value = {"status": "complete"}

        context = service.get_current_workspace_context({
            "id": "user-1",
            "account_type": "system_admin",
        })

        self.assertEqual(context["accountType"], "system_admin")

    def test_member_cannot_update_company_settings(self):
        service = WorkspaceService()
        service.get_current_workspace_context = Mock(return_value={
            "workspaceId": "workspace-1",
            "workspaceName": "NITRUS",
            "workspaceRole": "member",
            "onboardingStatus": "complete",
            "accountType": "workspace_user",
        })

        with self.assertRaises(HTTPException) as err:
            service.salvar_empresa_settings({"id": "user-1"}, {"name": "Nova empresa"})

        self.assertEqual(err.exception.status_code, 403)

    def test_patch_cannot_complete_onboarding(self):
        service = WorkspaceService()
        service.get_current_workspace_context = Mock(return_value={
            "workspaceId": "workspace-1",
            "workspaceName": "NITRUS",
            "workspaceRole": "owner",
            "onboardingStatus": "in_progress",
            "accountType": "workspace_user",
        })

        with self.assertRaises(HTTPException) as err:
            service.atualizar_onboarding({"id": "user-1"}, {"status": "complete"})

        self.assertEqual(err.exception.status_code, 400)


if __name__ == "__main__":
    unittest.main()
