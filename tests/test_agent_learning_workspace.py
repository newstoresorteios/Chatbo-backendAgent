from app.services import agent_learning_service as module
from app.services.agent_learning_service import AgentLearningService


class Result:
    def __init__(self, data):
        self.data = data


class Query:
    def __init__(self, store, table):
        self.store = store
        self.table = table
        self.filters = []
        self.payload = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def neq(self, *_args):
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def execute(self):
        rows = [
            row for row in self.store[self.table]
            if all(row.get(key) == value for key, value in self.filters)
        ]
        if self.payload is not None:
            for row in rows:
                row.update(self.payload)
        return Result(rows)


class FakeSupabase:
    def __init__(self):
        self.rows = {
            "ai_learning_insights": [{
                "id": 1, "tenant_id": "newstore", "workspace_id": "workspace-1",
                "title": "Ajustar busca", "insight_text": "Pergunte a faixa de preco",
                "evidence_count": 3, "confidence": 0.8, "importance": 0.7,
                "status": "pending_review", "metadata": {},
            }],
            "ai_agent_instruction_extensions": [{
                "id": 2, "tenant_id": "newstore", "workspace_id": "workspace-1",
                "extension_key": "learning:persona:1", "category": "persona",
                "instruction_text": "Pergunte a faixa de preco", "status": "active",
                "metadata": {},
            }],
            "ai_attendance_reviews": [{
                "id": 3, "tenant_id": "newstore", "workspace_id": "workspace-1",
                "outcome": "failure", "failure_codes": ["catalog_miss"],
                "customer_text": "texto cliente", "agent_reply": "texto agente",
                "created_at": "2026-09-15T12:00:00+00:00",
            }],
            "ai_learning_cases": [{
                "id": 4, "tenant_id": "newstore", "workspace_id": "workspace-1",
                "case_key": "learning:catalog_miss", "failure_codes": ["catalog_miss"],
                "customer_excerpt": "cliente", "bad_reply": "ruim", "correction": "corrija",
                "status": "active", "importance": 0.9,
            }],
        }

    def table(self, name):
        return Query(self.rows, name)


def test_overview_is_scoped_and_exposes_operational_learning(monkeypatch):
    fake = FakeSupabase()
    fake.rows["ai_learning_insights"].append({
        **fake.rows["ai_learning_insights"][0], "id": 9, "workspace_id": "workspace-2"
    })
    monkeypatch.setattr(module, "supabase", fake)

    result = AgentLearningService().overview(workspace_id="workspace-1")

    assert result["workspaceId"] == "workspace-1"
    assert [item["id"] for item in result["pendingInsights"]] == [1]
    assert result["counts"]["activeCases"] == 1
    assert result["recentReviews"][0]["failureCodes"] == ["catalog_miss"]
    assert "signals" not in result["recentReviews"][0]


def test_active_extension_can_be_retired_only_in_workspace(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(module, "supabase", fake)

    result = AgentLearningService().retire_extension(
        2, workspace_id="workspace-1", actor="operator@example.com", reason="Regra desatualizada"
    )

    assert result["extension"]["status"] == "superseded"
    assert result["extension"]["rejectionReason"] == "Regra desatualizada"
    assert result["extension"]["metadata"]["retired_by"] == "operator@example.com"
