import sys
import types
import unittest
from copy import deepcopy
from unittest.mock import patch


fastapi_stub = sys.modules.get("fastapi") or types.ModuleType("fastapi")


class HTTPException(Exception):
    def __init__(self, status_code: int, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


fastapi_stub.HTTPException = getattr(fastapi_stub, "HTTPException", HTTPException)
fastapi_stub.Header = getattr(fastapi_stub, "Header", lambda default=None, **_kwargs: default)
sys.modules.setdefault("fastapi", fastapi_stub)
HTTPException = fastapi_stub.HTTPException

supabase_stub = types.ModuleType("supabase")
supabase_stub.Client = object
supabase_stub.ClientOptions = object
supabase_stub.create_client = lambda *_args, **_kwargs: object()
sys.modules.setdefault("supabase", supabase_stub)

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

from app.core.internal_auth import require_nitrus_internal_token
from app.services.persona_runtime_service import PersonaRuntimeService


class FakeWorkspaceRepository:
    def __init__(self, workspace_ids: set[str]):
        self.workspace_ids = workspace_ids

    def buscar_workspace(self, workspace_id: str) -> dict | None:
        if workspace_id in self.workspace_ids:
            return {"id": workspace_id, "name": "Workspace"}
        return None


class FakePersonaRepository:
    def __init__(self, rows: list[dict]):
        self.rows = deepcopy(rows)

    def listar_por_workspace(self, workspace_id: str) -> list[dict]:
        return [deepcopy(row) for row in self.rows if row.get("workspace_id") == workspace_id]


def persona_row(workspace_id: str, status: str = "active", persona_id: str = "persona-a") -> dict:
    return {
        "id": persona_id,
        "workspace_id": workspace_id,
        "status": status,
        "version": 3,
        "name": "Persona Consultiva",
        "role": "Consultora",
        "language": "pt-BR",
        "tone": "formal",
        "greeting": "Olá",
        "introduction": "Sou sua consultora.",
        "customer_address_style": "senhor/senhora",
        "closing_message": "Até logo",
        "target_audience": "Empresas",
        "customer_profile": "Compradores recorrentes",
        "sales_goals": ["Qualificar necessidade"],
        "qualification_rules": ["Perguntar orçamento"],
        "opportunity_criteria": ["Necessidade identificada"],
        "objection_handling": {"preço": "explicar valor"},
        "upsell_rules": ["Sugerir complemento"],
        "recommendation_rules": ["Usar catálogo disponível"],
        "human_handoff_criteria": ["Negociação"],
        "escalation_rules": ["Prioridade alta"],
        "restrictions": ["Não inventar preço"],
        "examples": [{"customerMessage": "Olá", "expectedResponse": "Como posso ajudar?"}],
        "activated_at": "2026-07-15T10:00:00+00:00",
        "updated_at": "2026-07-15T10:01:00+00:00",
        "created_by": "internal-user-that-must-not-leak",
    }


class PersonaRuntimeServiceTest(unittest.TestCase):
    def service(self, rows: list[dict], workspaces: set[str] = {"workspace-a", "workspace-b"}) -> PersonaRuntimeService:
        return PersonaRuntimeService(
            persona_repo=FakePersonaRepository(rows),
            workspace_repo=FakeWorkspaceRepository(workspaces),
        )

    def test_active_persona_is_normalized_and_versioned(self):
        runtime = self.service([persona_row("workspace-a")]).get_active_runtime("workspace-a")

        self.assertIsNotNone(runtime)
        self.assertEqual(runtime.personaId, "persona-a")
        self.assertEqual(runtime.workspaceId, "workspace-a")
        self.assertEqual(runtime.version, 3)
        self.assertEqual(runtime.qualificationRules, ["Perguntar orçamento"])
        self.assertEqual(runtime.examples[0].expectedResponse, "Como posso ajudar?")
        self.assertNotIn("createdBy", runtime.model_dump())

    def test_draft_and_inactive_are_not_returned(self):
        service = self.service([
            persona_row("workspace-a", status="draft", persona_id="draft"),
            persona_row("workspace-a", status="inactive", persona_id="inactive"),
        ])

        self.assertIsNone(service.get_active_runtime("workspace-a"))

    def test_missing_persona_is_controlled(self):
        with self.assertRaises(HTTPException) as error:
            self.service([]).require_active_runtime("workspace-a")

        self.assertEqual(error.exception.status_code, 404)
        self.assertIn("Nenhuma Persona ativa", error.exception.detail)

    def test_workspace_isolation(self):
        rows = [persona_row("workspace-a"), persona_row("workspace-b", persona_id="persona-b")]
        service = self.service(rows)

        runtime = service.get_active_runtime("workspace-b")

        self.assertEqual(runtime.personaId, "persona-b")
        self.assertEqual(runtime.workspaceId, "workspace-b")

    def test_unknown_workspace_is_not_resolved(self):
        with self.assertRaises(HTTPException) as error:
            self.service([persona_row("workspace-a")]).get_active_runtime("unknown")

        self.assertEqual(error.exception.status_code, 404)
        self.assertEqual(error.exception.detail, "Workspace não encontrado.")

    def test_multiple_active_personas_is_invalid(self):
        with self.assertRaises(HTTPException) as error:
            self.service([
                persona_row("workspace-a", persona_id="persona-a"),
                persona_row("workspace-a", persona_id="persona-b"),
            ]).get_active_runtime("workspace-a")

        self.assertEqual(error.exception.status_code, 409)

    def test_invalid_jsonb_shapes_are_normalized_without_cross_workspace_data(self):
        row = persona_row("workspace-a")
        row.update({"sales_goals": {}, "objection_handling": [], "examples": [{"customer_message": "Oi"}]})

        runtime = self.service([row]).require_active_runtime("workspace-a")

        self.assertEqual(runtime.salesGoals, [])
        self.assertEqual(runtime.objectionHandling, {})
        self.assertEqual(runtime.examples, [])


class InternalAuthTest(unittest.TestCase):
    def test_token_is_required_and_compared_without_accepting_user_jwt(self):
        with patch("app.core.internal_auth.NITRUS_INTERNAL_API_TOKEN", "internal-token"):
            require_nitrus_internal_token("internal-token")
            with self.assertRaises(HTTPException) as error:
                require_nitrus_internal_token("user-jwt")

        self.assertEqual(error.exception.status_code, 401)

    def test_missing_server_token_is_not_fail_open(self):
        with patch("app.core.internal_auth.NITRUS_INTERNAL_API_TOKEN", None):
            with self.assertRaises(HTTPException) as error:
                require_nitrus_internal_token("anything")

        self.assertEqual(error.exception.status_code, 401)


if __name__ == "__main__":
    unittest.main()
