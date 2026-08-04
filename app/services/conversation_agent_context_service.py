"""Agrega dados das tabelas ai_* para o painel de atendimento."""

from __future__ import annotations

import logging
import re
from typing import Any

from fastapi import HTTPException

from app.repositories.conversa_repository import ConversaRepository
from app.services.ai.resources import (
    agent_responses_service,
    contact_memories_service,
    conversation_statuses_service,
    pix_payments_service,
    remarketing_contacts_service,
)

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


def _first_item(result: dict | None) -> dict | None:
    items = (result or {}).get("items") or []
    return items[0] if items else None


def _safe_listar(service, usuario: dict, **kwargs) -> dict:
    try:
        return service.listar(usuario, **kwargs)
    except Exception as exc:
        logger.warning("Falha ao listar %s: %s", getattr(service.repo, "table", "?"), exc)
        return {"items": [], "page": 1, "pageSize": kwargs.get("page_size", 50), "total": 0}


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

    def _find_contact(self, usuario: dict, sender_keys: list[str]) -> dict | None:
        for key in sender_keys:
            for column in ("sender_key", "sender_phone", "identity_key"):
                row = _first_item(
                    _safe_listar(
                        remarketing_contacts_service,
                        usuario,
                        page=1,
                        page_size=1,
                        filters={column: key},
                    )
                )
                if row:
                    return row
        return None

    def _find_status(self, usuario: dict, contact_id: Any) -> dict | None:
        if contact_id is None:
            return None
        return _first_item(
            _safe_listar(
                conversation_statuses_service,
                usuario,
                page=1,
                page_size=1,
                filters={"contact_id": contact_id},
            )
        )

    def obter(self, conversation_id: str, usuario: dict, workspace_id: str | None) -> dict:
        conversa = self.conversas.obter(conversation_id, workspace_id=workspace_id)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")

        sender_keys = _sender_key_candidates(conversa)
        contact_row = self._find_contact(usuario, sender_keys)
        status_row = self._find_status(usuario, contact_row.get("id") if contact_row else None)

        memories_items: list[dict] = []
        responses_items: list[dict] = []
        pix_items: list[dict] = []

        for key in sender_keys:
            if not memories_items:
                memories_items = (
                    _safe_listar(
                        contact_memories_service,
                        usuario,
                        page=1,
                        page_size=5,
                        filters={"sender_key": key, "status": "active"},
                    ).get("items")
                    or []
                )
            if not responses_items:
                responses_items = (
                    _safe_listar(
                        agent_responses_service,
                        usuario,
                        page=1,
                        page_size=3,
                        filters={"sender_key": key},
                    ).get("items")
                    or []
                )
            if not pix_items:
                pix_items = (
                    _safe_listar(
                        pix_payments_service,
                        usuario,
                        page=1,
                        page_size=5,
                        filters={"sender_key": key},
                    ).get("items")
                    or []
                )

        if not pix_items:
            pix_items = (
                _safe_listar(
                    pix_payments_service,
                    usuario,
                    page=1,
                    page_size=5,
                    filters={"conversation_id": conversation_id},
                ).get("items")
                or []
            )

        return {
            "conversationId": conversation_id,
            "senderKey": sender_keys[0] if sender_keys else None,
            "contact": _map_contact(contact_row),
            "status": _map_status(status_row),
            "memories": [_map_memory(row) for row in memories_items[:5]],
            "pixPayments": [_map_pix(row) for row in pix_items[:5]],
            "recentResponses": [_map_response(row) for row in responses_items[:3]],
        }
