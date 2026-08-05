"""Envio humano via Brevo — mesmo caminho do NSAgentForSorteios (app/brevo_client.py)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import (
    BREVO_AGENT_EMAIL,
    BREVO_AGENT_ID,
    BREVO_AGENT_NAME,
    BREVO_API_KEY,
    BREVO_RECEIVED_FROM,
    BREVO_REPLY_MODE,
    BREVO_SEND_URL,
    BREVO_SENDER_NUMBER,
)
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

BREVO_WHATSAPP_SEND_URL = "https://api.brevo.com/v3/whatsapp/sendMessage"
BREVO_CONVERSATIONS_SEND_URL = "https://api.brevo.com/v3/conversations/messages"


def _normalize_phone(phone: str | None) -> str | None:
    """Igual NSAgent repository.normalize_phone — só dígitos."""
    if not phone:
        return None
    if phone.startswith("whatsapp:"):
        phone = phone.split(":", 1)[1]
    digits = "".join(ch for ch in phone if ch.isdigit())
    return digits or None


class BrevoOutboundService:
    def configurado(self) -> bool:
        return bool(BREVO_API_KEY)

    def status(self) -> dict:
        agent = self._agent_payload()
        return {
            "configured": self.configurado(),
            "replyMode": (BREVO_REPLY_MODE or "auto").lower(),
            "hasAgentId": bool(BREVO_AGENT_ID),
            "hasAgentEmail": bool(BREVO_AGENT_EMAIL and BREVO_AGENT_NAME),
            "hasSenderNumber": bool(_normalize_phone(BREVO_SENDER_NUMBER)),
            "agentReady": bool(agent),
        }

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

    def _query_inbound(self, column: str, value: str) -> dict | None:
        try:
            rows = (
                supabase.table("ai_inbound_messages")
                .select("*")
                .eq(column, value)
                .order("created_at", desc=True)
                .limit(1)
                .execute()
                .data
                or []
            )
            return rows[0] if rows else None
        except Exception as exc:
            logger.warning("Brevo lookup %s=%s falhou: %s", column, value, exc)
            return None

    def _lookup_inbound(self, conversa: dict) -> dict | None:
        keys: list[str] = []
        for field in ("external_thread_id", "contact_phone"):
            value = conversa.get(field)
            if value and str(value).strip():
                keys.append(str(value).strip())

        for key in keys:
            for column in ("conversation_id", "sender_key", "sender_phone", "visitor_id"):
                row = self._query_inbound(column, key)
                if row:
                    return row

        # Fallback pelo preview da última mensagem (mesmo padrão do bridge).
        preview = str(conversa.get("last_message") or "").strip()
        if len(preview) >= 12:
            needle = preview[:48].replace("%", "")
            for table, column in (
                ("ai_inbound_messages", "text"),
                ("ai_agent_responses", "reply_text"),
            ):
                try:
                    rows = (
                        supabase.table(table)
                        .select("*")
                        .ilike(column, f"%{needle}%")
                        .order("created_at", desc=True)
                        .limit(3)
                        .execute()
                        .data
                        or []
                    )
                except Exception:
                    continue
                for row in rows:
                    if table == "ai_inbound_messages":
                        return row
                    inbound_id = row.get("inbound_id")
                    if inbound_id is not None:
                        found = self._query_inbound("id", str(inbound_id))
                        if found:
                            return found
        return None

    def _post(self, url: str, payload: dict[str, Any]) -> dict:
        headers = {
            "accept": "application/json",
            "content-type": "application/json",
            "api-key": BREVO_API_KEY or "",
        }
        with httpx.Client(timeout=25) as client:
            resp = client.post(url, json=payload, headers=headers)
        try:
            body = resp.json()
        except Exception:
            body = {"text": (resp.text or "")[:500]}
        logger.info(
            "Brevo POST %s → HTTP %s ok=%s",
            url.split("/")[-1],
            resp.status_code,
            200 <= resp.status_code < 300,
        )
        return {
            "ok": 200 <= resp.status_code < 300,
            "status_code": resp.status_code,
            "body": body,
        }

    def _send_conversations(self, visitor_id: str, text: str) -> dict:
        agent = self._agent_payload()
        if not agent:
            return {
                "sent": False,
                "reason": "Configure BREVO_AGENT_ID ou BREVO_AGENT_EMAIL + BREVO_AGENT_NAME no Render (iguais ao NSAgent)",
            }
        result = self._post(
            BREVO_CONVERSATIONS_SEND_URL,
            {"text": text, "visitorId": visitor_id, **agent},
        )
        if result["ok"]:
            return {"sent": True, "channel": "brevo_conversations", "provider": result["body"]}
        detail = result["body"]
        msg = None
        if isinstance(detail, dict):
            msg = detail.get("message") or detail.get("error") or str(detail)[:200]
        return {
            "sent": False,
            "reason": f"Brevo Conversations HTTP {result['status_code']}: {msg or 'falha'}",
            "provider": detail,
        }

    def _send_whatsapp(self, sender_phone: str, text: str) -> dict:
        recipient = _normalize_phone(sender_phone)
        sender = _normalize_phone(BREVO_SENDER_NUMBER)
        if not recipient:
            return {"sent": False, "reason": "Telefone do cliente ausente no inbound Brevo"}
        if not sender:
            return {
                "sent": False,
                "reason": "BREVO_SENDER_NUMBER não configurado no Render (igual ao NSAgent)",
            }
        send_url = (BREVO_SEND_URL or BREVO_WHATSAPP_SEND_URL).strip()
        result = self._post(
            send_url,
            {
                "contactNumbers": [recipient],
                "senderNumber": sender,
                "text": text,
            },
        )
        if result["ok"]:
            return {"sent": True, "channel": "brevo_whatsapp", "provider": result["body"]}
        detail = result["body"]
        msg = None
        if isinstance(detail, dict):
            msg = detail.get("message") or detail.get("error") or str(detail)[:200]
        return {
            "sent": False,
            "reason": f"Brevo WhatsApp HTTP {result['status_code']}: {msg or 'falha'}",
            "provider": detail,
        }

    def enviar_para_conversa(self, conversa: dict, content: str) -> dict:
        """Espelha NSAgent send_brevo_reply (modo texto)."""
        if not self.configurado():
            return {
                "sent": False,
                "reason": "BREVO_API_KEY não configurada no backend (Render). Use a mesma do NSAgentForSorteios.",
            }

        text = (content or "").strip()
        if not text:
            return {"sent": False, "reason": "Mensagem vazia"}

        inbound = self._lookup_inbound(conversa) or {}
        channel = str(inbound.get("channel") or conversa.get("channel") or "whatsapp").lower()
        visitor_id = inbound.get("visitor_id")
        sender_phone = inbound.get("sender_phone") or conversa.get("contact_phone")
        mode = (BREVO_REPLY_MODE or "auto").lower()

        logger.info(
            "Brevo send channel=%s visitor=%s phone=%s mode=%s conversa=%s",
            channel,
            bool(visitor_id),
            bool(_normalize_phone(str(sender_phone) if sender_phone else None)),
            mode,
            conversa.get("id"),
        )

        # Mesma ordem do NSAgentForSorteios/app/brevo_client.py::send_brevo_reply
        if channel == "whatsapp" and sender_phone and mode != "conversations":
            return self._send_whatsapp(str(sender_phone), text)

        if channel in {"instagram", "facebook", "widget"} and visitor_id:
            return self._send_conversations(str(visitor_id), text)

        if channel in {"instagram", "facebook", "widget"}:
            return {
                "sent": False,
                "reason": "visitorId Brevo ausente para Instagram/Facebook — sincronize o inbound do NSAgent",
            }

        if visitor_id:
            return self._send_conversations(str(visitor_id), text)

        if sender_phone:
            return self._send_whatsapp(str(sender_phone), text)

        return {
            "sent": False,
            "reason": (
                "Não encontrei visitorId/telefone do Brevo para esta conversa. "
                "Confirme que ai_inbound_messages está no mesmo Supabase do ChatBô."
            ),
        }


brevo_outbound_service = BrevoOutboundService()
