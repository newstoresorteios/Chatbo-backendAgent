import pytest
from fastapi import HTTPException

from app.services import agent_trace_service as module
from app.services.agent_trace_service import AgentTraceService


def trace_row(*, response_id: int = 7, workspace_id: str = "workspace-1", sent: bool = True) -> dict:
    return {
        "id": response_id,
        "inbound_id": 11,
        "workspace_id": workspace_id,
        "channel": "whatsapp",
        "intent": "product_search",
        "handoff_required": False,
        "safety_reason": None,
        "provider_send_ok": sent,
        "created_at": "2026-09-14T12:00:00+00:00",
        "provider_response": {
            "_agent_metadata": {
                "response_source": "catalog",
                "persona_runtime": {
                    "workspace_id": workspace_id,
                    "persona_version_id": 4,
                    "runtime_configuration_keys": ["historyTurns"],
                },
                "turn_runtime": {
                    "trace_id": "inbox-22",
                    "execution_path": "normal",
                    "processing_total_ms": 321.4,
                    "openai_call_count": 1,
                    "tray_call_count": 2,
                    "database_call_count": 3,
                    "openai_input_tokens": 120,
                    "openai_output_tokens": 30,
                    "fallback_reasons": [],
                    "stage_durations_ms": {"catalog": 80.2},
                    "tray_tools": [{"tool": "search_products", "ok": True, "elapsed_ms": 42}],
                    "openai_calls": [{"call_type": "decision", "elapsed_ms": 90}],
                    "inbound": {"text_preview": "Quero um relógio"},
                    "outbound": {"reply_preview": "Separei estas opções"},
                },
            }
        },
    }


class FakeTraceRepository:
    def __init__(self):
        self.rows = [trace_row()]
        self.list_args = None

    def listar(self, workspace_id: str, **kwargs):
        self.list_args = {"workspace_id": workspace_id, **kwargs}
        return list(self.rows)

    def obter(self, response_id: int, workspace_id: str):
        return next((row for row in self.rows if row["id"] == response_id and row["workspace_id"] == workspace_id), None)


@pytest.fixture
def service(monkeypatch):
    monkeypatch.setattr(
        module.workspace_service,
        "get_current_workspace_context",
        lambda _user: {"workspaceId": "workspace-1", "workspaceRole": "supervisor"},
    )
    instance = AgentTraceService()
    instance.repo = FakeTraceRepository()
    return instance


def test_trace_list_is_scoped_and_summarized(service):
    result = service.listar({}, limit=20, before=None, channel="whatsapp", outcome=None)

    assert service.repo.list_args["workspace_id"] == "workspace-1"
    assert result["items"][0]["traceId"] == "inbox-22"
    assert result["items"][0]["durationMs"] == 321.4
    assert result["items"][0]["inputPreview"] == "Quero um relógio"
    assert "provider_response" not in result["items"][0]


def test_trace_detail_only_returns_safe_runtime_parts(service):
    result = service.obter({}, 7)

    assert result["stages"] == {"catalog": 80.2}
    assert result["trayTools"][0]["tool"] == "search_products"
    assert result["personaRuntime"]["workspace_id"] == "workspace-1"


def test_trace_from_another_workspace_is_not_found(service):
    service.repo.rows = [trace_row(workspace_id="workspace-2")]
    with pytest.raises(HTTPException) as error:
        service.obter({}, 7)
    assert error.value.status_code == 404


def test_filtered_pagination_resumes_after_last_returned_match(service):
    service.repo.rows = [trace_row(response_id=i) for i in range(10, 3, -1)]
    result = service.listar({}, limit=2, before=None, channel=None, outcome="delivered")
    assert [row["id"] for row in result["items"]] == [10, 9]
    assert result["hasNext"] is True
    assert result["nextCursor"].endswith("|9")
