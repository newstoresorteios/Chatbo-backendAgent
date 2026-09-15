from copy import deepcopy

import pytest
from fastapi import HTTPException
from pydantic import ValidationError

from app.schemas.agent_registry import AgentRuntimeConfiguration
from app.services import agent_registry_service as module
from app.services.agent_registry_service import AgentRegistryService


class FakeRepository:
    def __init__(self):
        self.row = {
            "id": "agent-1",
            "workspace_id": "workspace-1",
            "config_version": 2,
            "configuration": {
                "legacyProvider": "brevo",
                "runtime": {
                    "schemaVersion": 1,
                    "values": {"historyTurns": 18, "catalogShortlistSize": 4},
                },
            },
            "updated_at": "2026-09-14T12:00:00+00:00",
        }
        self.published = None

    def obter_por_workspace(self, workspace_id: str):
        assert workspace_id == "workspace-1"
        return deepcopy(self.row)

    def publicar_configuracao(self, **payload):
        self.published = deepcopy(payload)
        self.row["configuration"] = deepcopy(payload["configuration"])
        self.row["config_version"] += 1
        return {"version": self.row["config_version"]}

    def listar_versoes_configuracao(self, workspace_id: str):
        assert workspace_id == "workspace-1"
        return []


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(
        module.workspace_service,
        "get_current_workspace_context",
        lambda _user: {
            "workspaceId": "workspace-1",
            "workspaceRole": "owner",
        },
    )
    instance = AgentRegistryService()
    instance.repo = FakeRepository()
    return instance


def test_configuration_fills_defaults_and_exposes_schema(service):
    result = service.obter_configuracao({"id": "user-1"})

    assert result["version"] == 2
    assert result["values"]["historyTurns"] == 18
    assert result["values"]["catalogShortlistSize"] == 4
    assert result["values"]["maxReplyChars"] == 900
    assert {field["key"] for field in result["fields"]} == set(result["values"])


def test_publish_is_validated_versioned_and_attributed(service):
    values = AgentRuntimeConfiguration(historyTurns=20).model_dump()
    result = service.publicar_configuracao(
        {"id": "user-1"},
        {"expectedVersion": 2, "values": values},
    )

    assert result["version"] == 3
    assert service.repo.published["expected_version"] == 2
    assert service.repo.published["created_by"] == "user-1"
    assert service.repo.published["configuration"]["runtime"]["values"]["historyTurns"] == 20
    assert service.repo.published["configuration"]["legacyProvider"] == "brevo"


def test_configuration_rejects_unknown_or_unsafe_fields():
    with pytest.raises(ValidationError):
        AgentRuntimeConfiguration.model_validate({"openaiApiKey": "secret"})


def test_legacy_agent_update_cannot_bypass_validation(service):
    with pytest.raises(HTTPException) as error:
        service.atualizar_agente_empresa(
            {"id": "user-1"},
            {"configuration": {"openaiApiKey": "secret"}},
        )

    assert error.value.status_code == 400
