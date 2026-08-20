"""Envio humano no Instagram via Graph API (mesmo caminho do NSAgent)."""

from __future__ import annotations

import logging
from typing import Any

import httpx

from app.config.settings import META_IG_BUSINESS_ACCOUNT_ID, META_PAGE_ACCESS_TOKEN

logger = logging.getLogger(__name__)


def _recipient_id(conversa: dict, inbound: dict | None) -> str | None:
    inbound = inbound or {}
    for value in (
        inbound.get("sender_external_id"),
        inbound.get("visitor_id"),
        str(inbound.get("sender_key") or "").split(":")[-1],
        str(conversa.get("contact_phone") or "").split(":")[-1],
        str(conversa.get("external_thread_id") or "").split(":")[-1],
    ):
        text = str(value or "").strip()
        if text and text.lower() not in {"instagram", "ig", "whatsapp"}:
            return text
    return None


def is_meta_instagram(conversa: dict, inbound: dict | None) -> bool:
    inbound = inbound or {}
    provider = str(inbound.get("provider") or "").lower()
    thread = str(conversa.get("external_thread_id") or inbound.get("conversation_id") or "")
    sender_key = str(conversa.get("contact_phone") or inbound.get("sender_key") or "")
    return (
        provider == "meta"
        or thread.startswith("ig:")
        or sender_key.startswith("instagram:")
    )


def enviar_para_conversa(conversa: dict, content: str, inbound: dict | None = None) -> dict[str, Any]:
    token = (META_PAGE_ACCESS_TOKEN or "").strip()
    if not token:
        return {
            "sent": False,
            "reason": "META_PAGE_ACCESS_TOKEN ausente no Render. Use o mesmo token do NSAgent.",
        }
    text = (content or "").strip()
    if not text:
        return {"sent": False, "reason": "Mensagem vazia"}
    recipient_id = _recipient_id(conversa, inbound)
    if not recipient_id:
        return {"sent": False, "reason": "Não encontrei o IGSID do Instagram para enviar."}

    ig_account_id = (META_IG_BUSINESS_ACCOUNT_ID or "").strip()
    payload = {
        "recipient": {"id": recipient_id},
        "messaging_type": "RESPONSE",
        "message": {"text": text[:2000]},
    }
    endpoints: list[str] = []
    if token.startswith("IGAA"):
        endpoints.append("https://graph.instagram.com/v21.0/me/messages")
        if ig_account_id:
            endpoints.append(f"https://graph.instagram.com/v21.0/{ig_account_id}/messages")
    elif ig_account_id:
        endpoints.append(f"https://graph.instagram.com/v21.0/{ig_account_id}/messages")
        endpoints.append("https://graph.instagram.com/v21.0/me/messages")
    endpoints.append("https://graph.facebook.com/v21.0/me/messages")

    last_status = 0
    last_body: Any = {}
    with httpx.Client(timeout=20) as client:
        for url in endpoints:
            resp = client.post(
                url,
                params={"access_token": token},
                json=payload,
                headers={"Authorization": f"Bearer {token}"},
            )
            last_status = resp.status_code
            try:
                last_body = resp.json()
            except Exception:
                last_body = {"raw": (resp.text or "")[:200]}
            if resp.status_code < 300:
                logger.info("Meta IG send ok conversa=%s endpoint=%s", conversa.get("id"), url.split("/v21.0/", 1)[-1])
                return {
                    "sent": True,
                    "provider": "meta",
                    "status_code": resp.status_code,
                    "endpoint": url.split("/v21.0/", 1)[-1],
                }

    logger.error("Meta IG send failed conversa=%s status=%s body=%s", conversa.get("id"), last_status, last_body)
    error = last_body.get("error") if isinstance(last_body, dict) else last_body
    return {
        "sent": False,
        "reason": f"Instagram Graph HTTP {last_status}: {error}",
        "provider": last_body,
    }
