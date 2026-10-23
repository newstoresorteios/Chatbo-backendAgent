"""YCloud pilot channel registration and signed-event processing."""

from __future__ import annotations

import logging
import os
import re
import uuid
from datetime import datetime, timezone
from datetime import timedelta

from fastapi import HTTPException

from app.providers.whatsapp_ycloud import YCloudProvider, normalize_phone
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.repositories.platform_repository import PlatformRepository

logger = logging.getLogger(__name__)
_HUMAN_REQUEST = re.compile(r"\b(atendente|pessoa\s+real|falar\s+com\s+(?:um\s+)?humano)\b", re.I)
_HUMAN_DENIAL = re.compile(
    r"\b(n[aã]o|nunca)\s+(?:quero|preciso|desejo|gostaria)\b.{0,60}"
    r"\b(atendente|humano|pessoa\s+real)\b", re.I,
)
_STATUS_ORDER = {"accepted": 0, "sent": 1, "failed": 2, "delivered": 3, "read": 4}


def _wants_human(content: str) -> bool:
    return bool(_HUMAN_REQUEST.search(content)) and not bool(_HUMAN_DENIAL.search(content))


def _event_time(value: str | None) -> datetime:
    if not value:
        return datetime.now(timezone.utc)
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("Horário do evento YCloud inválido") from exc
    if parsed.tzinfo is None:
        raise ValueError("Horário do evento YCloud sem fuso")
    return parsed.astimezone(timezone.utc)


def _as_time(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return _event_time(value)
    except ValueError:
        return None


def _content(message: dict) -> str:
    kind = str(message.get("type") or "").lower()
    if kind == "text":
        return str((message.get("text") or {}).get("body") or "").strip()
    if kind in {"image", "video", "audio", "document", "sticker"}:
        media = message.get(kind) or {}
        label = str(media.get("filename") or kind)
        caption = str(media.get("caption") or "").strip()
        return f"[{kind}: {label}] {caption}".strip()
    if kind == "button":
        return str((message.get("button") or {}).get("text") or "[botão]")
    return f"[{kind or 'mensagem'} recebida]"


class YCloudService:
    def __init__(self, *, provider: YCloudProvider | None = None,
                 channels=None, conversations=None, messages=None, bot_handler=None):
        self.provider = provider
        self.channels = channels if channels is not None else PlatformRepository()
        self.conversations = conversations if conversations is not None else ConversaRepository()
        self.messages = messages if messages is not None else MensagemRepository()
        self.bot_handler = bot_handler

    def _provider(self) -> YCloudProvider:
        if self.provider is None:
            self.provider = YCloudProvider(
                os.getenv("YCLOUD_API_KEY", ""), os.getenv("YCLOUD_PHONE_NUMBER", ""),
                os.getenv("YCLOUD_WABA_ID", ""), os.getenv("YCLOUD_PHONE_NUMBER_ID"),
            )
        return self.provider

    def _matching_channels(self) -> list[dict]:
        provider = self._provider()
        matches = []
        for row in self.channels.list_canais():
            if row.get("provider") != "ycloud" or str(row.get("waba_id") or "") != provider.waba_id:
                continue
            try:
                if normalize_phone(row.get("display_phone") or row.get("phone") or "") == provider.phone_number:
                    matches.append(row)
            except ValueError:
                continue
        return matches

    def status(self, workspace_id: str) -> dict:
        try:
            provider = self._provider()
            matches = self._matching_channels()
            channel = next((row for row in matches
                            if str(row.get("workspace_id") or "") == str(workspace_id)), None)
            claimed_elsewhere = bool(matches and not channel)
        except ValueError:
            provider, channel, claimed_elsewhere = None, None, False
        from app.config.settings import PUBLIC_API_URL

        return {
            "configured": provider is not None and not claimed_elsewhere
            and bool(os.getenv("YCLOUD_WEBHOOK_SECRET", "").strip()),
            "connected": bool(channel and channel.get("connected")),
            "provider": "ycloud",
            "phone": provider.phone_number if provider and not claimed_elsewhere else None,
            "canalId": channel.get("id") if channel else None,
            "providerStatus": channel.get("provider_status") if channel else "pending",
            "webhookUrl": f"{PUBLIC_API_URL.rstrip('/')}/webhooks/ycloud" if PUBLIC_API_URL else None,
        }

    def connect(self, workspace_id: str, name: str) -> dict:
        if not workspace_id:
            raise HTTPException(403, "Empresa não resolvida")
        if not os.getenv("YCLOUD_WEBHOOK_SECRET", "").strip():
            raise HTTPException(503, "Configure YCLOUD_WEBHOOK_SECRET antes de ativar o canal")
        provider = self._provider()
        remote = provider.validate_number()
        existing = self._matching_channels()
        if any(str(row.get("workspace_id") or "") != str(workspace_id) for row in existing):
            raise HTTPException(409, "Número YCloud já vinculado a outra empresa")
        data = {
            "type": "whatsapp", "name": name.strip(), "provider": "ycloud",
            "provider_status": "active", "connected": True, "workspace_id": workspace_id,
            "waba_id": provider.waba_id, "phone_number_id": str(remote["id"]),
            "display_phone": provider.phone_number,
            "last_activity": datetime.now(timezone.utc).isoformat(),
        }
        if existing:
            row = self.channels.update_canal(str(existing[0]["id"]), data)
        else:
            data.update(id=f"ch-yc-{uuid.uuid4().hex[:12]}", messages_today=0)
            row = self.channels.create_canal(data)
        return {
            "id": str(row["id"]), "type": "whatsapp", "name": row["name"],
            "provider": "ycloud", "connected": True, "providerStatus": "active",
            "phone": provider.phone_number,
        }

    def _channel_for_inbound(self, message: dict) -> dict | None:
        provider = self._provider()
        if str(message.get("wabaId") or "") != provider.waba_id:
            return None
        try:
            if normalize_phone(message.get("to") or "") != provider.phone_number:
                return None
        except ValueError:
            return None
        return next((row for row in self._matching_channels()
                     if row.get("connected") and row.get("workspace_id")), None)

    @staticmethod
    def ensure_text_window(conversation: dict) -> None:
        latest = _as_time(conversation.get("last_customer_message_at"))
        now = datetime.now(timezone.utc)
        if latest is None or latest > now + timedelta(minutes=5) or now - latest >= timedelta(hours=24):
            raise HTTPException(409, "Janela de 24 horas encerrada; use um template aprovado")

    def send_for_conversation(self, conversation: dict, body: str) -> dict:
        provider = self._provider()
        channel = self.channels.get_canal(str(conversation.get("canal_id") or ""))
        if not channel or channel.get("provider") != "ycloud" or not channel.get("connected"):
            return {"sent": False, "reason": "Canal YCloud não conectado"}
        if str(channel.get("workspace_id") or "") != str(conversation.get("workspace_id") or ""):
            return {"sent": False, "reason": "Canal YCloud incompatível com a empresa"}
        if str(channel.get("waba_id") or "") != provider.waba_id:
            return {"sent": False, "reason": "WABA YCloud incompatível"}
        try:
            if normalize_phone(channel.get("display_phone") or "") != provider.phone_number:
                return {"sent": False, "reason": "Número YCloud incompatível"}
        except ValueError:
            return {"sent": False, "reason": "Número YCloud inválido"}
        self.ensure_text_window(conversation)
        try:
            message_id = provider.send_text(conversation.get("contact_phone") or "", body)
        except Exception:
            logger.exception("Falha de envio pelo canal YCloud %s", channel.get("id"))
            return {"sent": False, "reason": "Falha ao enviar pela YCloud"}
        return {"sent": True, "provider": "ycloud", "providerStatus": "accepted",
                "externalId": f"ycloud:{message_id}"}

    def process_event(self, event: dict) -> dict:
        event_type = event.get("type")
        if event_type == "whatsapp.inbound_message.received":
            processed, job = self.ingest_inbound(event.get("whatsappInboundMessage") or {})
            return {"processed": int(processed), "bot_jobs": [job] if job else []}
        if event_type == "whatsapp.message.updated":
            return {"processed": int(self.update_status(event.get("whatsappMessage") or {})), "bot_jobs": []}
        if event_type == "whatsapp.smb.history":
            return {"processed": int(self.ingest_history(event)), "bot_jobs": []}
        return {"processed": 0, "bot_jobs": []}

    def ingest_history(self, event: dict) -> bool:
        """Store one coexistence history message without bot, unread or handoff effects."""
        inbound = event.get("whatsappInboundMessage")
        message = inbound or event.get("whatsappMessage") or {}
        direction = "inbound" if inbound else "outbound"
        provider = self._provider()
        business, customer_key = ("to", "from") if inbound else ("from", "to")
        if str(message.get("wabaId") or "") != provider.waba_id:
            return False
        channel = next((row for row in self._matching_channels()
                        if row.get("connected") and row.get("workspace_id")), None)
        raw_id = str(message.get("id") or message.get("wamid") or "").strip()
        if not channel or not raw_id:
            return False
        try:
            if normalize_phone(message.get(business) or "") != provider.phone_number:
                return False
            customer = normalize_phone(message.get(customer_key) or "")
            stamped = _event_time(message.get("sendTime") or message.get("createTime"))
        except ValueError:
            return False
        content = _content(message)
        if not content:
            return False
        name = str((message.get("customerProfile") or {}).get("name") or "").strip() or customer
        result = self.conversations.ingest_ycloud_history(
            channel_id=str(channel["id"]), workspace_id=str(channel["workspace_id"]),
            external_id=f"ycloud:{raw_id}", customer=customer, customer_name=name,
            content=content, sent_at=stamped.isoformat(), direction=direction,
        )
        if not result.get("inserted"):
            return False
        from app.services.inbox_cache import invalidate_conversa

        invalidate_conversa(str(result["conversation_id"]), str(channel["workspace_id"]))
        return True

    def ingest_inbound(self, message: dict) -> tuple[bool, tuple[str, str, str] | None]:
        channel = self._channel_for_inbound(message)
        raw_id = str(message.get("id") or "").strip()
        if not channel or not raw_id:
            return False, None
        external_id = f"ycloud:{raw_id}"
        try:
            customer = normalize_phone(message.get("from") or "")
            stamped = _event_time(message.get("sendTime"))
        except ValueError:
            return False, None
        content = _content(message)
        if not content:
            return False, None
        workspace_id = str(channel["workspace_id"])
        channel_id = str(channel["id"])
        result = self.conversations.ingest_ycloud_atomic(
            channel_id=channel_id, workspace_id=workspace_id, external_id=external_id,
            customer=customer,
            customer_name=str((message.get("customerProfile") or {}).get("name") or "").strip() or customer,
            content=content, sent_at=stamped.isoformat(), human_request=_wants_human(content),
        )
        if not result.get("inserted"):
            return False, None
        conversation_id = str(result["conversation_id"])
        from app.services.inbox_cache import invalidate_conversa

        invalidate_conversa(conversation_id, workspace_id)
        if not result.get("should_reply"):
            return True, None
        return True, (conversation_id, content, workspace_id)

    def reply_if_eligible(self, conversation_id: str, content: str, workspace_id: str) -> bool:
        conversation = self.conversations.obter(conversation_id, workspace_id=workspace_id)
        if not conversation or conversation.get("status") != "active" or conversation.get("assigned_to"):
            return False
        if conversation.get("bot_activated") is False:
            return False
        channel = self.channels.get_canal(str(conversation.get("canal_id") or ""))
        if not channel or channel.get("provider") != "ycloud" or not channel.get("connected", True):
            return False
        try:
            if self.bot_handler is None:
                from app.services.chatbot_service import chatbot_service

                result = chatbot_service.handle_inbound(conversation_id, content, "whatsapp")
            else:
                result = self.bot_handler(conversation_id, content, "whatsapp")
        except Exception:
            logger.exception("Bot YCloud falhou na conversa %s", conversation_id)
            result = None
        if result:
            return True
        current = self.conversations.obter(conversation_id, workspace_id=workspace_id)
        if current and current.get("status") == "active" and not current.get("assigned_to"):
            self.conversations.atualizar(conversation_id, {
                "status": "waiting", "bot_activated": False,
                "handoff_requested_at": datetime.now(timezone.utc).isoformat(),
                "handoff_reason": "bot_unavailable",
            }, workspace_id=workspace_id)
            from app.services.inbox_cache import invalidate_conversa

            invalidate_conversa(conversation_id, workspace_id)
        return False

    def update_status(self, payload: dict) -> bool:
        provider_id = str(payload.get("id") or "").strip()
        incoming = str(payload.get("status") or "").lower()
        if not provider_id or incoming not in _STATUS_ORDER:
            return False
        try:
            provider = self._provider()
            if not any(row.get("connected") for row in self._matching_channels()):
                return False
            if payload.get("wabaId") and str(payload["wabaId"]) != provider.waba_id:
                return False
            if payload.get("from") and normalize_phone(payload["from"]) != provider.phone_number:
                return False
        except ValueError:
            return False
        external_id = f"ycloud:{provider_id}"
        result = self.messages.record_ycloud_status(
            external_id, incoming, payload.get("wabaId"), payload.get("from"),
        )
        if result.get("updated"):
            from app.services.inbox_cache import invalidate_conversa

            invalidate_conversa(str(result["conversation_id"]), str(result["workspace_id"]))
        return bool(result.get("updated") or result.get("pending"))


ycloud_service = YCloudService()
