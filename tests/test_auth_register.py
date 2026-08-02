import unittest
from unittest.mock import Mock, patch

from fastapi import HTTPException

from app.services.auth_service import AuthService


class FakeUsuarioRepository:
    def __init__(self, existing: dict | None = None):
        self.existing = existing
        self.created: dict | None = None
        self.deleted: list[str] = []

    def buscar_por_email(self, email: str) -> dict | None:
        return self.existing

    def criar(self, dados: dict) -> dict:
        self.created = {"id": "user-1", **dados}
        return self.created

    def excluir(self, usuario_id: str) -> None:
        self.deleted.append(usuario_id)


class FakeTokenRepository:
    def __init__(self):
        self.saved: list[tuple[str, str]] = []

    def salvar_refresh(self, usuario_id, token_plain, expira_em) -> None:
        self.saved.append((usuario_id, token_plain))


def workspace_context() -> dict:
    return {
        "workspaceId": "workspace-1",
        "workspaceName": "Empresa Frontend",
        "workspaceRole": "owner",
        "onboardingStatus": "pending",
        "accountType": "workspace_user",
    }


class AuthRegisterTest(unittest.TestCase):
    def build_service(self, repository: FakeUsuarioRepository) -> AuthService:
        service = AuthService()
        service.repository = repository
        service.token_repository = FakeTokenRepository()
        return service

    def test_enterprise_register_creates_user_workspace_owner_settings_onboarding_and_session(self):
        repository = FakeUsuarioRepository()
        service = self.build_service(repository)
        fake_workspace = Mock()
        fake_workspace.criar_workspace_inicial.return_value = {"id": "workspace-1"}
        fake_workspace.get_current_workspace_context.return_value = workspace_context()

        with patch("app.services.auth_service.workspace_service", fake_workspace):
            response = service.register(
                name="Usuario Frontend",
                email="NOVO@EXAMPLE.COM",
                password="Senha123!",
                company="Empresa Frontend",
            )

        self.assertEqual(repository.created["email"], "novo@example.com")
        self.assertEqual(repository.created["nome"], "Usuario Frontend")
        self.assertEqual(repository.created["empresa"], "Empresa Frontend")
        fake_workspace.criar_workspace_inicial.assert_called_once_with(
            user_id="user-1",
            name="Empresa Frontend",
        )
        user = response["user"]
        self.assertTrue(response["token"])
        self.assertTrue(response["refreshToken"])
        self.assertEqual(user["accountType"], "workspace_user")
        self.assertEqual(user["workspaceId"], "workspace-1")
        self.assertEqual(user["workspaceName"], "Empresa Frontend")
        self.assertEqual(user["workspaceRole"], "owner")
        self.assertEqual(user["onboardingStatus"], "pending")

    def test_duplicate_email_is_blocked_before_creating_user(self):
        repository = FakeUsuarioRepository(existing={"id": "existing"})
        service = self.build_service(repository)

        with self.assertRaises(HTTPException) as err:
            service.register(
                name="Usuario",
                email="existente@example.com",
                password="Senha123!",
                company="Empresa",
            )

        self.assertEqual(err.exception.status_code, 409)
        self.assertIsNone(repository.created)

    def test_workspace_failure_compensates_created_user(self):
        repository = FakeUsuarioRepository()
        service = self.build_service(repository)
        fake_workspace = Mock()
        fake_workspace.criar_workspace_inicial.side_effect = RuntimeError("workspace failed")

        with patch("app.services.auth_service.workspace_service", fake_workspace):
            with self.assertRaises(RuntimeError):
                service.register(
                    name="Usuario",
                    email="novo@example.com",
                    password="Senha123!",
                    company="Empresa",
                )

        self.assertEqual(repository.deleted, ["user-1"])

    def test_session_failure_compensates_created_workspace_and_user(self):
        repository = FakeUsuarioRepository()
        service = self.build_service(repository)
        service.token_repository.salvar_refresh = Mock(side_effect=RuntimeError("refresh failed"))
        fake_workspace = Mock()
        fake_workspace.criar_workspace_inicial.return_value = {"id": "workspace-1"}
        fake_workspace.get_current_workspace_context.return_value = workspace_context()

        with patch("app.services.auth_service.workspace_service", fake_workspace):
            with self.assertRaises(RuntimeError):
                service.register(
                    name="Usuario",
                    email="novo@example.com",
                    password="Senha123!",
                    company="Empresa",
                )

        fake_workspace.excluir_workspace.assert_called_once_with("workspace-1")
        self.assertEqual(repository.deleted, ["user-1"])


if __name__ == "__main__":
    unittest.main()
