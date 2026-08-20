"""Marca atividade humana para o NSAgent pausar o bot (ai_human_takeover_state)."""

from __future__ import annotations

import logging
from datetime import datetime, timezone

from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)


def mark_human_active(conversa: dict, *, source: str) -> None:
    keys: list[str] = []
    for field in ("external_thread_id", "contact_phone"):
        value = str(conversa.get(field) or "").strip()
        if value and value not in keys:
            keys.append(value)
    if not keys:
        return
    now = datetime.now(timezone.utc).isoformat()
    for key in keys:
        try:
            supabase.table("ai_human_takeover_state").upsert(
                {
                    "state_key": key,
                    "conversation_key": keys[0],
                    "sender_key": conversa.get("contact_phone"),
                    "last_human_activity_at": now,
                    "takeover_detected_at": now,
                    "updated_at": now,
                    "metadata": {"source": source},
                },
                on_conflict="state_key",
            ).execute()
        except Exception as exc:
            logger.warning("Falha ao marcar takeover humano (%s): %s", key, exc)
