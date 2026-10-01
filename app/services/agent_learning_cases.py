"""Materialize manually reviewed incidents without mutating their evidence."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from fastapi import HTTPException


def _scoped(client, table: str, tenant_id: str, workspace_id: str):
    return client.table(table).select("*").eq("tenant_id", tenant_id).eq("workspace_id", workspace_id)


def prepare_reviewed_cases(client, extension: dict, *, tenant_id: str, workspace_id: str) -> dict | None:
    """Resolve every referenced review before activating the instruction.

    An absent or foreign review is the same conflict to the caller. We never
    silently shrink the approved evidence set or infer an incident's workspace.
    """
    metadata = extension.get("metadata") or {}
    insight_id = metadata.get("insight_id")
    if insight_id is None:
        return None  # An instruction written manually need not have incidents.
    rows = (_scoped(client, "ai_learning_insights", tenant_id, workspace_id)
            .eq("id", insight_id).limit(1).execute().data or [])
    if not rows:
        raise HTTPException(status_code=409, detail="Insight de origem indisponível neste workspace")
    insight = rows[0]
    source_ids = insight.get("source_review_ids") or []
    if not isinstance(source_ids, list) or not source_ids or any(
        isinstance(value, bool) or not isinstance(value, int) or value <= 0 for value in source_ids
    ):
        raise HTTPException(status_code=409, detail="Insight sem revisões de origem válidas; revise as evidências")
    review_ids = list(dict.fromkeys(source_ids))
    reviews = {}
    # A historical insight can accumulate more IDs than one PostgREST page/URL.
    for offset in range(0, len(review_ids), 100):
        rows = (_scoped(client, "ai_attendance_reviews", tenant_id, workspace_id)
                .in_("id", review_ids[offset:offset + 100]).execute().data or [])
        reviews.update({row["id"]: row for row in rows})
    if set(reviews) != set(review_ids):
        raise HTTPException(status_code=409, detail="Revisões de origem indisponíveis neste workspace; revise as evidências")
    primary_code = (insight.get("metadata") or {}).get("failure_code")
    cases = {}
    for review_id in review_ids:
        review = reviews[review_id]
        codes = review.get("failure_codes") or []
        if (not isinstance(codes, list) or not codes
                or any(not isinstance(code, str) or not code.strip() for code in codes)
                or (primary_code and primary_code not in codes)):
            raise HTTPException(status_code=409, detail="Revisão sem falha compatível com o insight; revise as evidências")
        for code in [primary_code] if primary_code else list(dict.fromkeys(codes)):
            customer = str(review.get("customer_text") or "")
            reply = str(review.get("agent_reply") or "")
            conversation = review.get("conversation_key")
            inbound_id, response_id = review.get("inbound_id"), review.get("response_id")
            # This identity matches NSAgent app.learning.cases, including legacy
            # incidents without recorded response/inbound IDs.
            identity = json.dumps(
                [conversation, response_id, inbound_id]
                if response_id is not None or inbound_id is not None
                else [conversation, customer, reply], ensure_ascii=False,
            )
            case_key = f"learning:{code}:{hashlib.sha256(identity.encode('utf-8')).hexdigest()[:24]}"
            if case_key in cases:
                cases[case_key]["metadata"]["source_review_ids"].append(review_id)
                continue
            cases[case_key] = {
                "tenant_id": tenant_id, "workspace_id": workspace_id,
                "case_key": case_key, "conversation_key": conversation,
                "failure_codes": [code], "customer_excerpt": customer[:400],
                "bad_reply": reply[:400], "status": "active", "insight_id": insight["id"],
                "importance": float(insight.get("importance") or 0.5),
                "metadata": {
                    "failure_code": code, "pattern_key": code, "immutable_incident": True,
                    "source_inbound_id": inbound_id, "source_response_id": response_id,
                    "source_review_ids": [review_id], "source_extension_id": extension["id"],
                    "reviewed_via": "chatbo_ui",
                },
            }
    return {"insight_id": insight["id"], "source_review_ids": list(source_ids), "cases": list(cases.values())}


def materialize_reviewed_cases(client, prepared: dict, extension: dict, *, actor: str) -> dict:
    """Insert immutable incidents; a retry only reads existing scoped records."""
    now = datetime.now(timezone.utc).isoformat()
    case_ids = []
    review_cases = {}
    for payload in prepared["cases"]:
        payload = {**payload, "metadata": {**payload["metadata"],
                   "reviewed_by": extension.get("approved_by") or actor,
                   "reviewed_at": extension.get("approved_at") or now},
                   "correction": str(extension.get("instruction_text") or "")[:800],
                   "created_at": now, "updated_at": now}

        def existing():
            return (_scoped(client, "ai_learning_cases", payload["tenant_id"], payload["workspace_id"])
                    .eq("case_key", payload["case_key"]).limit(1).execute().data or [])

        rows = existing()
        if not rows:
            try:
                rows = client.table("ai_learning_cases").insert(payload).execute().data or []
            except Exception as exc:
                # Only a proven unique violation plus a matching scoped record
                # is an idempotent concurrent retry; never swallow other errors.
                if str(getattr(exc, "code", None) or getattr(exc, "sqlstate", None)) != "23505":
                    raise
                rows = existing()
                if not rows:
                    raise
        if not rows or rows[0].get("id") is None:
            raise RuntimeError("learning_case_insert_missing_id")
        case_id = rows[0]["id"]
        case_ids.append(case_id)
        for review_id in payload["metadata"]["source_review_ids"]:
            review_cases.setdefault(str(review_id), []).append(case_id)
    return {"status": "complete", "insight_id": prepared["insight_id"],
            "source_review_ids": prepared["source_review_ids"], "case_ids": case_ids,
            "review_case_ids": review_cases}
