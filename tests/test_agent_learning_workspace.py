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
        self.exclusions = []
        self.memberships = []
        self.payload = None
        self.insert_payload = None

    def select(self, *_args):
        return self

    def eq(self, key, value):
        self.filters.append((key, value))
        return self

    def neq(self, key, value):
        self.exclusions.append((key, value))
        return self

    def in_(self, key, values):
        self.memberships.append((key, values))
        return self

    def insert(self, payload):
        self.insert_payload = payload
        return self

    def order(self, *_args, **_kwargs):
        return self

    def limit(self, *_args):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def execute(self):
        if self.insert_payload is not None:
            payload = {**self.insert_payload, "id": max((row["id"] for row in self.store[self.table]), default=0) + 1}
            self.store[self.table].append(payload)
            return Result([payload])
        rows = [
            row for row in self.store[self.table]
            if all(row.get(key) == value for key, value in self.filters)
            and all(row.get(key) != value for key, value in self.exclusions)
            and all(row.get(key) in values for key, values in self.memberships)
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
    from types import SimpleNamespace
    def rpc(name, args):
        assert name == "workspace_learning_overview"
        assert args == {"p_workspace_id": "workspace-1", "p_tenant_id": "newstore"}
        data = {"pendingInsights": [fake.rows["ai_learning_insights"][0]],
                "pendingExtensions": [], "activeExtensions": fake.rows["ai_agent_instruction_extensions"],
                "recentReviews": fake.rows["ai_attendance_reviews"], "activeCases": fake.rows["ai_learning_cases"],
                "counts": {"activeCases": 1, "reviewsLast24h": 125, "failuresLast24h": 42}}
        return SimpleNamespace(execute=lambda: Result(data))
    fake.rpc = rpc

    result = AgentLearningService().overview(workspace_id="workspace-1")

    assert result["workspaceId"] == "workspace-1"
    assert [item["id"] for item in result["pendingInsights"]] == [1]
    assert result["counts"]["activeCases"] == 1
    assert result["recentReviews"][0]["failureCodes"] == ["catalog_miss"]
    assert "signals" not in result["recentReviews"][0]
    assert result["counts"]["reviewsLast24h"] == 125  # Must not recount the displayed rows.
    assert result["counts"]["failuresLast24h"] == 42


def test_extension_approval_passes_workspace_to_atomic_rpc(monkeypatch):
    from types import SimpleNamespace
    calls = []
    row = {"id": 11, "tenant_id": "newstore", "workspace_id": "workspace-2", "status": "pending_review",
           "instruction_text": "Seja breve quando o cliente estiver com pressa."}
    def rpc(name, args):
        calls.append((name, args))
        return SimpleNamespace(execute=lambda: Result({**row, "status": "active"}))
    fake = FakeSupabase()
    fake.rows["ai_agent_instruction_extensions"].append(row)
    fake.rpc = rpc
    monkeypatch.setattr(module, "supabase", fake)
    result = AgentLearningService()._approve_extension_row(row, actor="operator")
    assert result["status"] == "active"
    assert row["metadata"]["policy_validation"]["status"] == "passed"
    assert calls == [("approve_workspace_instruction_extension", {"p_workspace_id": "workspace-2", "p_tenant_id": "newstore", "p_extension_id": 11, "p_actor": "operator"})]


def test_active_extension_can_be_retired_only_in_workspace(monkeypatch):
    fake = FakeSupabase()
    monkeypatch.setattr(module, "supabase", fake)

    result = AgentLearningService().retire_extension(
        2, workspace_id="workspace-1", actor="operator@example.com", reason="Regra desatualizada"
    )

    assert result["extension"]["status"] == "superseded"
    assert result["extension"]["rejectionReason"] == "Regra desatualizada"
    assert result["extension"]["metadata"]["retired_by"] == "operator@example.com"


def test_approval_blocks_conflicting_policy_before_rpc(monkeypatch):
    import pytest
    from fastapi import HTTPException
    fake = FakeSupabase()
    row = {"id": 99, "tenant_id": "newstore", "workspace_id": "workspace-1",
           "instruction_text": "Solicite a senha do cartão.", "status": "pending_review"}
    fake.rows["ai_agent_instruction_extensions"].append(row)
    fake.rpc = lambda *args: (_ for _ in ()).throw(AssertionError("must not activate"))
    monkeypatch.setattr(module, "supabase", fake)
    with pytest.raises(HTTPException) as exc:
        AgentLearningService()._approve_extension_row(row, actor="operator")
    assert exc.value.status_code == 409
    assert "payment_secret_collection" in exc.value.detail
    assert row["status"] == "pending_review"


def test_approval_blocks_duplicate_with_accents_or_punctuation(monkeypatch):
    import pytest
    from fastapi import HTTPException
    fake = FakeSupabase()
    row = {"id": 99, "tenant_id": "newstore", "workspace_id": "workspace-1",
           "instruction_text": "Pergunte a faixa de preço!", "status": "pending_review"}
    fake.rows["ai_agent_instruction_extensions"].append(row)
    monkeypatch.setattr(module, "supabase", fake)
    with pytest.raises(HTTPException) as exc:
        AgentLearningService()._approve_extension_row(row, actor="operator")
    assert "duplicate_active_instruction" in exc.value.detail


def test_agent_and_backend_use_identical_policy_contract():
    from pathlib import Path
    backend = Path(module.__file__).with_name("agent_instruction_policy.py")
    agent = backend.parents[3] / "NSAgentForSorteios" / "app" / "persona" / "instruction_policy.py"
    if agent.exists():
        assert backend.read_text(encoding="utf-8") == agent.read_text(encoding="utf-8")


def _approval_with_reviews(monkeypatch):
    from types import SimpleNamespace
    fake = FakeSupabase()
    insight = fake.rows["ai_learning_insights"][0]
    insight.update({"source_review_ids": [23, 24, 23], "metadata": {"failure_code": "catalog_miss"}})
    row = {"id": 11, "tenant_id": "newstore", "workspace_id": "workspace-1", "status": "pending_review",
           "instruction_text": "Confirme a referência exata informada antes de procurar o produto.",
           "metadata": {"insight_id": 1}}
    fake.rows["ai_agent_instruction_extensions"].append(row)
    for review_id, response_id in [(23, 101), (24, 102)]:
        fake.rows["ai_attendance_reviews"].append({
            "id": review_id, "tenant_id": "newstore", "workspace_id": "workspace-1",
            "conversation_key": "same-conversation", "inbound_id": response_id + 100,
            "response_id": response_id, "failure_codes": ["catalog_miss"],
            "outcome": "failure", "customer_text": "Mesma dúvida", "agent_reply": "Mesmo erro",
        })
    rpc_calls = []

    def rpc(name, args):
        rpc_calls.append((name, args))
        row.update({"status": "active", "approved_by": "reviewer", "approved_at": "2026-10-01T23:00:00Z"})
        return SimpleNamespace(execute=lambda: Result(dict(row)))

    fake.rpc = rpc
    monkeypatch.setattr(module, "supabase", fake)
    return fake, row, insight, rpc_calls


def test_manual_approval_preserves_distinct_turns_provenance_and_is_idempotent(monkeypatch):
    import copy
    import hashlib
    import json
    fake, row, insight, _ = _approval_with_reviews(monkeypatch)
    service = AgentLearningService()
    result = service.approve_extension(row["id"], workspace_id="workspace-1", actor="reviewer")
    cases = [case for case in fake.rows["ai_learning_cases"] if case.get("insight_id") == 1]
    assert len(cases) == 2  # Same conversation/text/category, different recorded turns.
    assert len({case["case_key"] for case in cases}) == 2
    identity = json.dumps(["same-conversation", 101, 201], ensure_ascii=False)
    assert cases[0]["case_key"] == "learning:catalog_miss:" + hashlib.sha256(identity.encode()).hexdigest()[:24]
    assert [case["metadata"]["source_review_ids"] for case in cases] == [[23], [24]]
    assert all(case["workspace_id"] == "workspace-1" and case["tenant_id"] == "newstore" for case in cases)
    assert all(case["metadata"]["reviewed_by"] == "reviewer" for case in cases)
    receipt = result["extension"]["metadata"]["case_materialization"]
    assert receipt["source_review_ids"] == insight["source_review_ids"] == [23, 24, 23]
    assert receipt["review_case_ids"] == {"23": [cases[0]["id"]], "24": [cases[1]["id"]]}
    original = copy.deepcopy(cases)
    row["instruction_text"] = "Confira a referência do produto com o cliente."
    service.approve_extension(row["id"], workspace_id="workspace-1", actor="another-reviewer")
    assert [case for case in fake.rows["ai_learning_cases"] if case.get("insight_id") == 1] == original
    assert insight["source_review_ids"] == [23, 24, 23]


def test_manual_approval_rejects_foreign_or_missing_review_before_activation(monkeypatch):
    import pytest
    from fastapi import HTTPException
    fake, row, insight, rpc_calls = _approval_with_reviews(monkeypatch)
    foreign = {**fake.rows["ai_attendance_reviews"][-1], "id": 90, "workspace_id": "workspace-2",
               "customer_text": "other workspace confidential"}
    fake.rows["ai_attendance_reviews"].append(foreign)
    for invalid_review_id in [90, 999]:
        insight["source_review_ids"] = [23, invalid_review_id]
        with pytest.raises(HTTPException) as exc:
            AgentLearningService().approve_extension(row["id"], workspace_id="workspace-1", actor="reviewer")
        assert exc.value.status_code == 409
    assert not rpc_calls
    assert row["status"] == "pending_review"
    assert len(fake.rows["ai_learning_cases"]) == 1


def test_promote_and_activate_uses_the_same_reviewed_case_hook(monkeypatch):
    fake, row, insight, _ = _approval_with_reviews(monkeypatch)
    insight["applied_extension_id"] = row["id"]
    result = AgentLearningService().promote_insight(
        insight["id"], workspace_id="workspace-1", activate=True, actor="reviewer",
    )
    assert result["activated"] is True
    assert result["insight"]["status"] == "applied"
    assert result["extension"]["metadata"]["case_materialization"]["source_review_ids"] == [23, 24, 23]
    assert len([case for case in fake.rows["ai_learning_cases"] if case.get("insight_id") == 1]) == 2


def test_manual_approval_does_not_truncate_evidence_beyond_one_query_batch(monkeypatch):
    fake, row, insight, _ = _approval_with_reviews(monkeypatch)
    sample = fake.rows["ai_attendance_reviews"][-1]
    ids = list(range(1000, 1141))
    fake.rows["ai_attendance_reviews"].extend([
        {**sample, "id": review_id, "response_id": review_id + 2000, "inbound_id": review_id + 3000}
        for review_id in ids
    ])
    insight["source_review_ids"] = ids
    result = AgentLearningService().approve_extension(row["id"], workspace_id="workspace-1", actor="reviewer")
    receipt = result["extension"]["metadata"]["case_materialization"]
    assert receipt["source_review_ids"] == ids
    assert len(receipt["case_ids"]) == len(receipt["review_case_ids"]) == 141


def test_partial_materialization_reports_active_state_and_retry_reconciles(monkeypatch):
    import copy
    import pytest
    from fastapi import HTTPException
    fake, row, _, _ = _approval_with_reviews(monkeypatch)
    real_execute = Query.execute
    attempts = 0

    def fail_second_insert(query):
        nonlocal attempts
        if query.table == "ai_learning_cases" and query.insert_payload is not None:
            attempts += 1
            if attempts == 2:
                raise TimeoutError("simulated database timeout")
        return real_execute(query)

    monkeypatch.setattr(Query, "execute", fail_second_insert)
    service = AgentLearningService()
    with pytest.raises(HTTPException) as exc:
        service.approve_extension(row["id"], workspace_id="workspace-1", actor="reviewer")
    assert exc.value.status_code == 502
    assert exc.value.detail["activated"] is True and exc.value.detail["retryable"] is True
    assert row["status"] == "active"
    saved = copy.deepcopy(fake.rows["ai_learning_cases"][-1])
    result = service.approve_extension(row["id"], workspace_id="workspace-1", actor="reviewer")
    assert result["extension"]["metadata"]["case_materialization"]["status"] == "complete"
    assert len([case for case in fake.rows["ai_learning_cases"] if case.get("insight_id") == 1]) == 2
    assert fake.rows["ai_learning_cases"][-2] == saved


def test_concurrent_insert_is_idempotent_only_for_proven_unique_violation(monkeypatch):
    import pytest
    from fastapi import HTTPException
    real_execute = Query.execute

    class DatabaseError(Exception):
        def __init__(self, code):
            self.code = code

    for error_code in ["23505", "08006"]:
        fake, row, _, _ = _approval_with_reviews(monkeypatch)

        def concurrent_insert(query):
            result = real_execute(query)
            if query.table == "ai_learning_cases" and query.insert_payload is not None:
                raise DatabaseError(error_code)
            return result

        monkeypatch.setattr(Query, "execute", concurrent_insert)
        if error_code == "23505":
            result = AgentLearningService().approve_extension(row["id"], workspace_id="workspace-1", actor="reviewer")
            assert result["extension"]["metadata"]["case_materialization"]["status"] == "complete"
        else:
            with pytest.raises(HTTPException) as exc:
                AgentLearningService().approve_extension(row["id"], workspace_id="workspace-1", actor="reviewer")
            assert exc.value.detail["code"] == "learning_case_materialization_pending"
