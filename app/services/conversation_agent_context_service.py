"""Agrega dados das tabelas ai_* para o painel de atendimento.

As tabelas do NSAgentForSorteios não têm workspace_id — consultas vão direto
ao Postgres compartilhado, sem filtro multi-tenant do ChatBô.
"""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import HTTPException

from app.repositories.conversa_repository import ConversaRepository
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)


def _digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def _sender_key_candidates(conversa: dict) -> list[str]:
    keys: list[str] = []
    for raw in (
        conversa.get("contact_phone"),
        conversa.get("external_thread_id"),
    ):
        if not raw:
            continue
        text = str(raw).strip()
        if text and text not in keys:
            keys.append(text)
        digits = _digits(text)
        if digits and digits not in keys:
            keys.append(digits)
        if digits.startswith("55") and len(digits) > 12:
            local = digits[2:]
            if local and local not in keys:
                keys.append(local)
        elif digits and len(digits) >= 10:
            with_cc = f"55{digits}"
            if with_cc not in keys:
                keys.append(with_cc)
    return keys


def _query_ai(table: str, filters: dict[str, Any], *, limit: int = 5, order: str = "created_at") -> list[dict]:
    try:
        query = supabase.table(table).select("*")
        for key, value in filters.items():
            if value is None or value == "":
                continue
            query = query.eq(key, value)
        query = query.order(order, desc=True).limit(limit)
        return query.execute().data or []
    except Exception as exc:
        logger.warning("Falha ao ler %s %s: %s", table, filters, exc)
        return []


def _first_match(table: str, columns: list[str], keys: list[str]) -> dict | None:
    for key in keys:
        for column in columns:
            rows = _query_ai(table, {column: key}, limit=1)
            if rows:
                return rows[0]
    return None


def _map_contact(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "identityKey": row.get("identity_key"),
        "senderKey": row.get("sender_key"),
        "senderPhone": row.get("sender_phone"),
        "senderName": row.get("sender_name"),
        "marketingStatus": row.get("marketing_status"),
        "messagingWindowExpiresAt": row.get("messaging_window_expires_at"),
        "channel": row.get("channel"),
    }


def _map_status(row: dict | None) -> dict | None:
    if not row:
        return None
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "stage": row.get("stage"),
        "productName": row.get("product_name"),
        "cartUrl": row.get("cart_url"),
        "paymentUrl": row.get("payment_url"),
        "orderId": row.get("order_id"),
        "cartSessionId": row.get("cart_session_id"),
        "lastCustomerMessageAt": row.get("last_customer_message_at"),
        "nextScheduledAt": row.get("next_scheduled_at"),
        "completionReason": row.get("completion_reason"),
        "completedAt": row.get("completed_at"),
    }


def _map_memory(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "memoryKey": row.get("memory_key"),
        "memoryKind": row.get("memory_kind"),
        "safeSummary": row.get("safe_summary"),
        "importance": row.get("importance"),
        "confidence": row.get("confidence"),
        "status": row.get("status"),
        "lastConfirmedAt": row.get("last_confirmed_at"),
        "useInInstructions": bool(row.get("use_in_instructions")),
    }


def _map_pix(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "status": row.get("status"),
        "amountCents": row.get("amount_cents"),
        "currency": row.get("currency") or "BRL",
        "description": row.get("description"),
        "expiresAt": row.get("expires_at") or row.get("date_of_expiration"),
        "paidAt": row.get("paid_at"),
        "qrCode": row.get("qr_code"),
        "conversationId": row.get("conversation_id"),
        "senderKey": row.get("sender_key"),
    }


def _map_response(row: dict) -> dict:
    return {
        "id": row.get("id"),
        "replyText": row.get("reply_text") or "",
        "intent": row.get("intent"),
        "handoffRequired": bool(row.get("handoff_required")),
        "safetyReason": row.get("safety_reason"),
        "providerSendOk": bool(row.get("provider_send_ok")),
        "createdAt": row.get("created_at"),
        "channel": row.get("channel"),
    }


class ConversationAgentContextService:
    def __init__(self):
        self.conversas = ConversaRepository()

    def obter(self, conversation_id: str, usuario: dict, workspace_id: str | None) -> dict:
        _ = usuario
        conversa = self.conversas.obter(conversation_id, workspace_id=workspace_id)
        if not conversa and workspace_id:
            conversa = self.conversas.obter(conversation_id, workspace_id=None)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")

        sender_keys = _sender_key_candidates(conversa)
        contact_row = _first_match(
            "ai_remarketing_contacts",
            ["sender_key", "sender_phone", "identity_key"],
            sender_keys,
        )
        status_row = None
        if contact_row and contact_row.get("id") is not None:
            status_rows = _query_ai(
                "ai_conversation_statuses",
                {"contact_id": contact_row.get("id")},
                limit=1,
                order="updated_at",
            )
            status_row = status_rows[0] if status_rows else None

        memories_items: list[dict] = []
        responses_items: list[dict] = []
        pix_items: list[dict] = []

        for key in sender_keys:
            if not memories_items:
                memories_items = _query_ai(
                    "ai_contact_memories",
                    {"sender_key": key, "status": "active"},
                    limit=5,
                    order="updated_at",
                )
            if not responses_items:
                responses_items = _query_ai(
                    "ai_agent_responses",
                    {"sender_key": key},
                    limit=3,
                )
            if not pix_items:
                pix_items = _query_ai(
                    "ai_pix_payments",
                    {"sender_key": key},
                    limit=5,
                    order="updated_at",
                )

        if not pix_items:
            thread_id = str(conversa.get("external_thread_id") or "").strip()
            for conv_key in (thread_id, conversation_id):
                if not conv_key:
                    continue
                pix_items = _query_ai(
                    "ai_pix_payments",
                    {"conversation_id": conv_key},
                    limit=5,
                    order="updated_at",
                )
                if pix_items:
                    break

        return {
            "conversationId": conversation_id,
            "senderKey": sender_keys[0] if sender_keys else None,
            "contact": _map_contact(contact_row),
            "status": _map_status(status_row),
            "memories": [_map_memory(row) for row in memories_items[:5]],
            "pixPayments": [_map_pix(row) for row in pix_items[:5]],
            "recentResponses": [_map_response(row) for row in responses_items[:3]],
        }
