"""Envio de mensagens humanas para o cliente via Brevo (mesmo canal do NSAgent)."""

from __future__ import annotations

import logging
import re
from typing import Any

import httpx

from app.config.settings import (
    BREVO_AGENT_EMAIL,
    BREVO_AGENT_ID,
    BREVO_AGENT_NAME,
    BREVO_API_KEY,
    BREVO_RECEIVED_FROM,
    BREVO_SENDER_NUMBER,
)
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

BREVO_WHATSAPP_SEND_URL = "https://api.brevo.com/v3/whatsapp/sendMessage"
BREVO_CONVERSATIONS_SEND_URL = "https://api.brevo.com/v3/conversations/messages"


def _digits(value: str | None) -> str:
    return re.sub(r"\D+", "", value or "")


def _normalize_phone(value: str | None) -> str | None:
    digits = _digits(value)
    if not digits:
        return None
    if digits.startswith("55") and len(digits) >= 12:
        return digits
    if len(digits) >= 10:
        return f"55{digits}"
    return digits


class BrevoOutboundService:
    def configurado(self) -> bool:
        return bool(BREVO_API_KEY)

    def _agent_payload(self) -> dict[str, str]:
        if BREVO_AGENT_ID:
            return {"agentId": BREVO_AGENT_ID}
        if BREVO_AGENT_EMAIL and BREVO_AGENT_NAME:
            return {
                "agentEmail": BREVO_AGENT_EMAIL,
                "agentName": BREVO_AGENT_NAME,
                "receivedFrom": BREVO_RECEIVED_FROM or BREVO_AGENT_NAME,
            }
        return {}

    def _lookup_inbound(self, conversa: dict) -> dict | None:
        keys: list[str] = []
        for field in ("external_thread_id", "contact_phone"):
            value = conversa.get(field)
            if value and str(value).strip():
                keys.append(str(value).strip())

        for key in keys:
            for column in ("conversation_id", "sender_key", "sender_phone", "visitor_id"):
                try:
                    rows = (
                        supabase.table("ai_inbound_messages")
                        .select("*")
                        .eq(column, key)
                        .order("created_at", desc=True)
                        .limit(1)
                        .execute()
                        .data
                        or []
                    )
                except Exception as exc:
                    logger.warning("Brevo lookup %s=%s falhou: %s", column, key, exc)
                    continue
                if rows:
                    return rows[0]
        return None

    def _post(self, url: str, payload: dict[str, Any]) -> dict:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": BREVO_API_KEY or "",
        }
        with httpx.Client(timeout=20) as client:
            resp = client.post(url, json=payload, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"text": (resp.text or "")[:500]}
        return {
            "ok": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "body": body,
        }

    def enviar_para_conversa(self, conversa: dict, content: str) -> dict:
        if not self.configurado():
            return {"sent": False, "reason": "BREVO_API_KEY não configurada"}

        text = (content or "").strip()
        if not text:
            return {"sent": False, "reason": "Mensagem vazia"}

        inbound = self._lookup_inbound(conversa) or {}
        channel = str(
            inbound.get("channel") or conversa.get("channel") or "whatsapp"
        ).lower()
        visitor_id = inbound.get("visitor_id")
        sender_phone = inbound.get("sender_phone") or conversa.get("contact_phone")
        if isinstance(sender_phone, str) and sender_phone.startswith("whatsapp:"):
            sender_phone = sender_phone.split(":", 1)[1]

        # Instagram / Facebook / widget → Conversations API
        if channel in {"instagram", "facebook", "widget", "webchat"} or visitor_id:
            if not visitor_id:
                return {"sent": False, "reason": "visitorId Brevo ausente para este contato"}
            agent = self._agent_payload()
            if not agent:
                return {
                    "sent": False,
                    "reason": "Configure BREVO_AGENT_ID ou BREVO_AGENT_EMAIL/NAME no Render",
                }
            result = self._post(
                BREVO_CONVERSATIONS_SEND_URL,
                {"text": text, "visitorId": visitor_id, **agent},
            )
            if result["ok"]:
                return {"sent": True, "channel": "brevo_conversations", "provider": result["body"]}
            return {
                "sent": False,
                "reason": f"Brevo Conversations HTTP {result['status_code']}",
                "provider": result["body"],
            }

        # WhatsApp → transactional
        recipient = _normalize_phone(sender_phone)
        sender = _normalize_phone(BREVO_SENDER_NUMBER)
        if not recipient:
            return {"sent": False, "reason": "Telefone do cliente ausente"}
        if not sender:
            return {"sent": False, "reason": "BREVO_SENDER_NUMBER não configurado"}

        result = self._post(
            BREVO_WHATSAPP_SEND_URL,
            {
                "contactNumbers": [recipient],
                "senderNumber": sender,
                "text": text,
            },
        )
        if result["ok"]:
            return {"sent": True, "channel": "brevo_whatsapp", "provider": result["body"]}
        return {
            "sent": False,
            "reason": f"Brevo WhatsApp HTTP {result['status_code']}",
            "provider": result["body"],
        }


brevo_outbound_service = BrevoOutboundService()
