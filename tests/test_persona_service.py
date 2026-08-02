import sys
import types
import unittest
from copy import deepcopy
from unittest.mock import Mock

fastapi_stub = sys.modules.get("fastapi") or types.ModuleType("fastapi")


class HTTPException(Exception):
    def __init__(self, status_code: int, detail):
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


fastapi_stub.HTTPException = getattr(fastapi_stub, "HTTPException", HTTPException)
HTTPException = fastapi_stub.HTTPException
sys.modules.setdefault("fastapi", fastapi_stub)

httpx_stub = types.ModuleType("httpx")
httpx_stub.post = lambda *_args, **_kwargs: None
sys.modules.setdefault("httpx", httpx_stub)

supabase_stub = types.ModuleType("supabase")
supabase_stub.Client = object
supabase_stub.create_client = lambda *_args, **_kwargs: object()
sys.modules.setdefault("supabase", supabase_stub)

dotenv_stub = types.ModuleType("dotenv")
dotenv_stub.load_dotenv = lambda *_args, **_kwargs: None
sys.modules.setdefault("dotenv", dotenv_stub)

from app.services.persona_service import PersonaService


class FakePersonaRepository:
    def __init__(self):
        self.personas = {}
        self.versions = []
        self.next_id = 1
        self.next_version_id = 1

    def listar_por_workspace(self, workspace_id: str) -> list[dict]:
        return [
            deepcopy(row)
            for row in self.personas.values()
            if row["workspace_id"] == workspace_id
        ]

    def buscar_por_id_workspace(self, persona_id: str, workspace_id: str) -> dict | None:
        row = self.personas.get(persona_id)
        if not row or row["workspace_id"] != workspace_id:
            return None
        return deepcopy(row)

    def buscar_ativa(self, workspace_id: str) -> dict | None:
        for row in self.personas.values():
            if row["workspace_id"] == workspace_id and row.get("status") == "active":
                return deepcopy(row)
        return None

    def criar(self, payload: dict) -> dict:
        row = deepcopy(payload)
        row["id"] = row.get("id") or f"persona-{self.next_id}"
        self.next_id += 1
        self.personas[row["id"]] = deepcopy(row)
        return deepcopy(row)

    def atualizar(self, persona_id: str, workspace_id: str, payload: dict) -> dict:
        row = self.personas[persona_id]
        if row["workspace_id"] != workspace_id:
            raise AssertionError("cross workspace update")
        row.update(deepcopy(payload))
        self.personas[persona_id] = row
        return deepcopy(row)

    def criar_versao(self, payload: dict) -> dict:
        row = deepcopy(payload)
        row["id"] = row.get("id") or f"version-{self.next_version_id}"
        self.next_version_id += 1
        self.versions.append(row)
        return deepcopy(row)

    def listar_versoes(self, persona_id: str, workspace_id: str) -> list[dict]:
        rows = [
            deepcopy(row)
            for row in self.versions
            if row["persona_id"] == persona_id and row["workspace_id"] == workspace_id
        ]
        return sorted(rows, key=lambda item: item["version"], reverse=True)

    def buscar_versao(self, persona_id: str, workspace_id: str, version: int) -> dict | None:
        for row in self.versions:
            if row["persona_id"] == persona_id and row["workspace_id"] == workspace_id and row["version"] == version:
                return deepcopy(row)
        return None


def persona_payload(name: str = "NITRUS Consultivo") -> dict:
    return {
        "name": name,
        "role": "Consultor comercial",
        "segment": "Varejo",
        "language": "pt-BR",
        "tone": "consultivo",
        "greeting": "Ola, como posso ajudar?",
        "targetAudience": "Clientes interessados em comprar",
        "salesGoals": ["Qualificar a necessidade"],
        "qualificationRules": ["Perguntar objetivo da compra"],
        "restrictions": ["Nao inventar preco"],
    }


class PersonaServiceTest(unittest.TestCase):
    def setUp(self):
        self.repo = FakePersonaRepository()
        self.ai = Mock(return_value="Resposta temporaria da persona.")
        self.service = PersonaService(repo=self.repo, ai_generator=self.ai)
        self.context = {
            "workspaceId": "workspace-a",
            "workspaceName": "NITRUS",
            "workspaceRole": "owner",
            "onboardingStatus": "complete",
            "accountType": "workspace_user",
        }
        self.service._context = Mock(return_value=self.context)
        self.user = {"id": "user-1"}

    def create_complete_persona(self, workspace_id: str = "workspace-a", name: str = "Persona") -> dict:
        previous_context = self.context
        self.context = {**self.context, "workspaceId": workspace_id}
        self.service._context = Mock(return_value=self.context)
        created = self.service.criar(self.user, persona_payload(name))
        self.context = previous_context
        self.service._context = Mock(return_value=self.context)
        return created

    def test_create_persona_as_draft_and_snapshot_created(self):
        created = self.service.criar(self.user, persona_payload())

        self.assertEqual(created["status"], "draft")
        self.assertEqual(created["version"], 1)
        self.assertEqual(len(self.repo.versions), 1)
        self.assertEqual(self.repo.versions[0]["change_type"], "created")

    def test_list_personas_is_scoped_by_workspace(self):
        own = self.create_complete_persona("workspace-a", "Own")
        self.create_complete_persona("workspace-b", "Other")

        result = self.service.listar(self.user)

        self.assertEqual(result["total"], 1)
        self.assertEqual(result["items"][0]["id"], own["id"])

    def test_update_increments_version_and_creates_snapshot(self):
        created = self.create_complete_persona()

        updated = self.service.atualizar(self.user, created["id"], {"tone": "objetivo"})

        self.assertEqual(updated["version"], 2)
        self.assertEqual(self.repo.versions[-1]["change_type"], "updated")
        self.assertEqual(self.repo.versions[-1]["version"], 2)

    def test_activate_persona_and_list_active(self):
        created = self.create_complete_persona()

        activated = self.service.ativar(self.user, created["id"])
        listed = self.service.listar(self.user)

        self.assertEqual(activated["status"], "active")
        self.assertEqual(listed["activePersonaId"], created["id"])
        self.assertEqual(self.repo.versions[-1]["change_type"], "activated")

    def test_activation_deactivates_previous_active_and_keeps_single_active(self):
        first = self.create_complete_persona(name="First")
        second = self.create_complete_persona(name="Second")

        self.service.ativar(self.user, first["id"])
        self.service.ativar(self.user, second["id"])

        active_rows = [
            row for row in self.repo.personas.values()
            if row["workspace_id"] == "workspace-a" and row["status"] == "active"
        ]
        self.assertEqual(len(active_rows), 1)
        self.assertEqual(active_rows[0]["id"], second["id"])
        self.assertEqual(self.repo.personas[first["id"]]["status"], "inactive")

    def test_activation_is_idempotent_without_extra_snapshot(self):
        created = self.create_complete_persona()
        self.service.ativar(self.user, created["id"])
        snapshot_count = len(self.repo.versions)

        self.service.ativar(self.user, created["id"])

        self.assertEqual(len(self.repo.versions), snapshot_count)

    def test_member_cannot_create_or_update(self):
        self.context = {**self.context, "workspaceRole": "member"}
        self.service._context = Mock(return_value=self.context)

        with self.assertRaises(HTTPException) as err:
            self.service.criar(self.user, persona_payload())

        self.assertEqual(err.exception.status_code, 403)

    def test_cross_workspace_persona_is_not_visible_or_mutable(self):
        other = self.create_complete_persona("workspace-b", "Other")

        with self.assertRaises(HTTPException) as read_err:
            self.service.obter(self.user, other["id"])
        with self.assertRaises(HTTPException) as update_err:
            self.service.atualizar(self.user, other["id"], {"tone": "tecnico"})
        with self.assertRaises(HTTPException) as activate_err:
            self.service.ativar(self.user, other["id"])
        with self.assertRaises(HTTPException) as version_err:
            self.service.listar_versoes(self.user, other["id"])

        self.assertEqual(read_err.exception.status_code, 404)
        self.assertEqual(update_err.exception.status_code, 404)
        self.assertEqual(activate_err.exception.status_code, 404)
        self.assertEqual(version_err.exception.status_code, 404)

    def test_workspace_id_in_body_is_ignored(self):
        created = self.service.criar(self.user, {**persona_payload(), "workspaceId": "workspace-b"})

        self.assertEqual(created["workspaceId"], "workspace-a")

    def test_list_and_get_versions(self):
        created = self.create_complete_persona()
        self.service.atualizar(self.user, created["id"], {"tone": "profissional"})

        versions = self.service.listar_versoes(self.user, created["id"])
        version = self.service.obter_versao(self.user, created["id"], 1)

        self.assertEqual([item["version"] for item in versions], [2, 1])
        self.assertEqual(version["version"], 1)

    def test_activation_validates_required_fields(self):
        created = self.service.criar(self.user, {"name": "Incompleta"})

        with self.assertRaises(HTTPException) as err:
            self.service.ativar(self.user, created["id"])

        self.assertEqual(err.exception.status_code, 400)
        self.assertIn("missingFields", err.exception.detail)

    def test_temporary_test_does_not_persist_or_change_active(self):
        created = self.create_complete_persona()
        active = self.service.ativar(self.user, created["id"])
        snapshot_count = len(self.repo.versions)

        response = self.service.testar(self.user, {
            "persona": persona_payload("Temporaria"),
            "customerMessage": "Preciso de ajuda para escolher.",
        })

        self.assertFalse(response["persisted"])
        self.assertFalse(response["activated"])
        self.assertEqual(self.repo.personas[active["id"]]["status"], "active")
        self.assertEqual(len(self.repo.versions), snapshot_count)
        self.ai.assert_called_once()


if __name__ == "__main__":
    unittest.main()
