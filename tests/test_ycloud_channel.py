"""Contracts for the dedicated YCloud pilot channel."""

import hashlib
import hmac
import importlib
import importlib.util
import json
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException


def _ycloud():
    assert importlib.util.find_spec("app.providers.whatsapp_ycloud") is not None, "YCloud provider ausente"
    return importlib.import_module("app.providers.whatsapp_ycloud")


class _Response:
    def __init__(self, payload: dict):
        self.payload = payload

    def raise_for_status(self):
        return None

    def json(self):
        return self.payload


def test_webhook_signature_uses_raw_body_and_rejects_replay():
    ycloud = _ycloud()
    body = b'{"type":"whatsapp.inbound_message.received","id":"evt-1"}'
    timestamp = 1_700_000_000
    digest = hmac.new(b"secret", f"{timestamp}.".encode() + body, hashlib.sha256).hexdigest()
    header = f"t={timestamp},s={digest}"

    assert ycloud.verify_signature(body, header, "secret", now=timestamp + 30)
    assert not ycloud.verify_signature(body + b" ", header, "secret", now=timestamp + 30)
    assert not ycloud.verify_signature(body, header, "secret", now=timestamp + 301)
    assert not ycloud.verify_signature(body, "", "secret", now=timestamp)


def test_number_validation_requires_exact_connected_identity(monkeypatch):
    ycloud = _ycloud()
    calls = []

    def get(url, *, headers, timeout):
        calls.append((url, headers, timeout))
        return _Response({
            "id": "phone-id-1", "phoneNumber": "+5543996676633",
            "wabaId": "waba-1", "status": "CONNECTED",
            "displayPhoneNumber": "+55 43 99667-6633",
        })

    monkeypatch.setattr("requests.get", get)
    provider = ycloud.YCloudProvider(
        api_key="pilot-key", phone_number="+5543996676633",
        waba_id="waba-1", phone_number_id="phone-id-1",
    )
    result = provider.validate_number()

    assert result["id"] == "phone-id-1"
    assert calls == [(
        "https://api.ycloud.com/v2/whatsapp/phoneNumbers/waba-1/%2B5543996676633",
        {"X-API-Key": "pilot-key", "Accept": "application/json"}, 15,
    )]


@pytest.mark.parametrize("field,value", [
    ("phoneNumber", "+5511999999999"),
    ("wabaId", "another-waba"),
    ("id", "another-phone-id"),
    ("status", "PENDING"),
])
def test_number_validation_rejects_mismatch_or_inactive(monkeypatch, field, value):
    ycloud = _ycloud()
    payload = {
        "id": "phone-id-1", "phoneNumber": "+5543996676633",
        "wabaId": "waba-1", "status": "CONNECTED",
    }
    payload[field] = value
    monkeypatch.setattr("requests.get", lambda *args, **kwargs: _Response(payload))
    provider = ycloud.YCloudProvider("pilot-key", "+5543996676633", "waba-1", "phone-id-1")

    with pytest.raises(ValueError):
        provider.validate_number()


def test_outbound_text_uses_pilot_sender_and_returns_provider_id(monkeypatch):
    ycloud = _ycloud()
    sent = []

    def post(url, *, headers, json, timeout):
        sent.append((url, headers, json, timeout))
        return _Response({"id": "out-1", "status": "accepted"})

    monkeypatch.setattr("requests.post", post)
    provider = ycloud.YCloudProvider("pilot-key", "+5543996676633", "waba-1")

    assert provider.send_text("+5511999999999", "Olá") == "out-1"
    assert sent == [(
        "https://api.ycloud.com/v2/whatsapp/messages",
        {"X-API-Key": "pilot-key", "Accept": "application/json"},
        {"from": "+5543996676633", "to": "+5511999999999", "type": "text", "text": {"body": "Olá"}},
        20,
    )]


class _Channels:
    def __init__(self, rows=None):
        self.rows = list(rows or [])

    def list_canais(self):
        return list(self.rows)

    def get_canal(self, channel_id):
        return next((row for row in self.rows if row["id"] == channel_id), None)

    def create_canal(self, data):
        row = dict(data)
        self.rows.append(row)
        return row

    def update_canal(self, channel_id, data):
        row = self.get_canal(channel_id)
        row.update(data)
        return row


class _Conversations:
    def __init__(self):
        self.rows = []
        self.message_store = None

    def ingest_ycloud_atomic(self, *, channel_id, workspace_id, external_id, customer,
                             customer_name, content, sent_at, human_request):
        messages = self.message_store
        if messages.obter_por_external_id(external_id):
            return {"inserted": False}
        row = self.obter_por_thread(channel_id, customer)
        if row is None:
            row = self.criar({
                "canal_id": channel_id, "external_thread_id": customer, "contact_phone": customer,
                "customer_name": customer_name, "channel": "whatsapp", "provider": "ycloud",
                "status": "active", "bot_activated": True, "unread_count": 0,
                "last_message": "", "last_message_at": sent_at,
                "last_customer_message_at": sent_at,
            }, workspace_id)
        messages.criar({"conversa_id": row["id"], "workspace_id": workspace_id,
                        "external_id": external_id, "content": content, "sender": "customer",
                        "direction": "inbound", "status": "delivered", "provider_status": "received",
                        "created_at": sent_at})
        patch = {"unread_count": int(row.get("unread_count") or 0) + 1}
        if sent_at > str(row.get("last_customer_message_at") or ""):
            patch["last_customer_message_at"] = sent_at
        if sent_at >= str(row.get("last_message_at") or ""):
            patch.update(last_message=content, last_message_at=sent_at)
        if human_request:
            patch.update(status="waiting", bot_activated=False,
                         handoff_requested_at=sent_at, handoff_reason="customer_requested_human")
        elif row.get("status") == "closed" and not row.get("assigned_to"):
            patch.update(status="active", bot_activated=True)
        self.atualizar(row["id"], patch, workspace_id)
        return {"inserted": True, "conversation_id": row["id"],
                "should_reply": row.get("status") == "active" and not row.get("assigned_to")
                and row.get("bot_activated") is not False and not human_request}

    def ingest_ycloud_history(self, *, channel_id, workspace_id, external_id, customer,
                              customer_name, content, sent_at, direction):
        messages = self.message_store
        if messages.obter_por_external_id(external_id):
            return {"inserted": False}
        row = self.obter_por_thread(channel_id, customer)
        if row is None:
            row = self.criar({
                "canal_id": channel_id, "external_thread_id": customer, "contact_phone": customer,
                "customer_name": customer_name, "channel": "whatsapp", "provider": "ycloud",
                "status": "closed", "bot_activated": True, "unread_count": 0,
                "last_message": "", "last_message_at": sent_at,
            }, workspace_id)
        inbound = direction == "inbound"
        messages.criar({"conversa_id": row["id"], "workspace_id": workspace_id,
                        "external_id": external_id, "content": content,
                        "sender": "customer" if inbound else "agent", "direction": direction,
                        "created_at": sent_at})
        return {"inserted": True, "conversation_id": row["id"]}

    def obter_por_thread(self, channel_id, thread_id):
        return next((row for row in self.rows if row["canal_id"] == channel_id
                     and row["external_thread_id"] == thread_id), None)

    def criar(self, data, workspace_id=None):
        row = {**data, "id": f"conv-{len(self.rows) + 1}", "workspace_id": workspace_id}
        self.rows.append(row)
        return row

    def atualizar(self, conversation_id, data, workspace_id=None, **kwargs):
        row = next(row for row in self.rows if row["id"] == conversation_id)
        assert row["workspace_id"] == workspace_id
        row.update(data)
        return row

    def obter(self, conversation_id, workspace_id=None):
        return next((row for row in self.rows if row["id"] == conversation_id
                     and (workspace_id is None or row["workspace_id"] == workspace_id)), None)


class _Messages:
    def __init__(self):
        self.rows = []
        self.conversations = None
        self.pending = {}

    def attach_ycloud_outbound(self, message_id, external_id, workspace_id):
        row = next(row for row in self.rows if row["id"] == message_id)
        row.update(external_id=external_id, provider_status=self.pending.pop(external_id, "accepted"))
        row["status"] = "sending" if row["provider_status"] == "accepted" else row["provider_status"]
        return row

    def record_ycloud_status(self, external_id, status, waba_id, sender_number):
        ranks = {"accepted": 0, "sent": 1, "failed": 2, "delivered": 3, "read": 4}
        row = self.obter_por_external_id(external_id)
        if row is None:
            if ranks[status] > ranks.get(self.pending.get(external_id), -1):
                self.pending[external_id] = status
            return {"pending": True}
        if ranks[status] <= ranks.get(row.get("provider_status"), -1):
            return {"updated": False}
        row.update(provider_status=status, status=status)
        conversation = self.conversations.obter(row["conversa_id"])
        return {"updated": True, "conversation_id": conversation["id"],
                "workspace_id": conversation["workspace_id"]}

    def obter_por_external_id(self, external_id):
        return next((row for row in self.rows if row.get("external_id") == external_id), None)

    def criar(self, data):
        if self.obter_por_external_id(data.get("external_id")):
            raise ValueError("duplicate key value violates unique constraint")
        row = {**data, "id": f"msg-{len(self.rows) + 1}"}
        self.rows.append(row)
        return row

    def atualizar_por_external_id(self, external_id, data):
        row = self.obter_por_external_id(external_id)
        if row:
            row.update(data)
        return row


def _service(channels=None, conversations=None, messages=None, bot_handler=None):
    from app.services.ycloud_service import YCloudService

    provider = type("Provider", (), {
        "phone_number": "+5543996676633", "waba_id": "waba-1", "phone_number_id": "phone-id-1",
        "validate_number": lambda self: {"id": "phone-id-1", "wabaId": "waba-1",
                                         "phoneNumber": "+5543996676633", "status": "CONNECTED"},
    })()
    conversations = conversations if conversations is not None else _Conversations()
    messages = messages if messages is not None else _Messages()
    conversations.message_store = messages
    messages.conversations = conversations
    return YCloudService(
        provider=provider, channels=channels or _Channels(),
        conversations=conversations, messages=messages,
        bot_handler=bot_handler,
    )


def test_connect_validates_before_persisting_and_scopes_workspace(monkeypatch):
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "test-secret")
    channels = _Channels()
    service = _service(channels=channels)

    result = service.connect("workspace-a", "Piloto")

    assert result["provider"] == "ycloud"
    assert result["connected"] is True
    assert channels.rows[0]["workspace_id"] == "workspace-a"
    assert "api_key" not in channels.rows[0]
    assert "access_token" not in channels.rows[0]


def test_connect_rejects_number_already_bound_to_other_workspace(monkeypatch):
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "test-secret")
    channels = _Channels([{
        "id": "other", "type": "whatsapp", "provider": "ycloud",
        "workspace_id": "workspace-b", "waba_id": "waba-1", "display_phone": "+5543996676633",
    }])
    service = _service(channels=channels)

    with pytest.raises(Exception) as error:
        service.connect("workspace-a", "Piloto")

    assert getattr(error.value, "status_code", None) == 409
    assert len(channels.rows) == 1


def _inbound(message_id="in-1", sent_at="2026-10-23T12:00:00Z", phone="5543996676633"):
    return {
        "type": "whatsapp.inbound_message.received",
        "whatsappInboundMessage": {
            "id": message_id, "wamid": "wamid." + message_id, "wabaId": "waba-1",
            "from": "5511999999999", "to": phone, "sendTime": sent_at,
            "type": "text", "text": {"body": "Preciso de ajuda"},
            "customerProfile": {"name": "Cliente Piloto"},
        },
    }


def test_inbound_persists_once_and_returns_one_bot_job():
    channels = _Channels([{
        "id": "pilot", "type": "whatsapp", "provider": "ycloud", "connected": True,
        "workspace_id": "workspace-a", "waba_id": "waba-1", "display_phone": "+5543996676633",
    }])
    conversations, messages = _Conversations(), _Messages()
    service = _service(channels, conversations, messages)

    first = service.process_event(_inbound())
    second = service.process_event(_inbound())

    assert first["processed"] == 1
    assert len(first["bot_jobs"]) == 1
    assert second == {"processed": 0, "bot_jobs": []}
    assert len(conversations.rows) == 1
    assert conversations.rows[0]["canal_id"] == "pilot"
    assert conversations.rows[0]["workspace_id"] == "workspace-a"
    assert conversations.rows[0]["provider"] == "ycloud"
    assert conversations.rows[0]["unread_count"] == 1
    assert messages.rows[0]["external_id"] == "ycloud:in-1"
    assert messages.rows[0]["sender"] == "customer"


def test_inbound_rejects_different_business_number_without_creating_conversation():
    channels = _Channels([{
        "id": "pilot", "type": "whatsapp", "provider": "ycloud", "connected": True,
        "workspace_id": "workspace-a", "waba_id": "waba-1", "display_phone": "+5543996676633",
    }])
    conversations, messages = _Conversations(), _Messages()
    service = _service(channels, conversations, messages)

    assert service.process_event(_inbound(phone="5511888888888")) == {"processed": 0, "bot_jobs": []}
    assert conversations.rows == []
    assert messages.rows == []


def test_older_inbound_does_not_rewind_customer_window_or_preview():
    channels = _Channels([{
        "id": "pilot", "type": "whatsapp", "provider": "ycloud", "connected": True,
        "workspace_id": "workspace-a", "waba_id": "waba-1", "display_phone": "+5543996676633",
    }])
    conversations, messages = _Conversations(), _Messages()
    service = _service(channels, conversations, messages)
    service.process_event(_inbound("new", "2026-10-23T12:00:00Z"))
    service.process_event(_inbound("old", "2026-10-22T12:00:00Z"))

    assert conversations.rows[0]["last_customer_message_at"] == "2026-10-23T12:00:00+00:00"
    assert conversations.rows[0]["last_message_at"] == "2026-10-23T12:00:00+00:00"
    assert len(messages.rows) == 2


def test_explicit_human_request_waits_without_starting_bot():
    channels = _Channels([{
        "id": "pilot", "type": "whatsapp", "provider": "ycloud", "connected": True,
        "workspace_id": "workspace-a", "waba_id": "waba-1", "display_phone": "+5543996676633",
    }])
    conversations, messages = _Conversations(), _Messages()
    service = _service(channels, conversations, messages)
    event = _inbound()
    event["whatsappInboundMessage"]["text"]["body"] = "Quero falar com atendente"

    result = service.process_event(event)

    assert result == {"processed": 1, "bot_jobs": []}
    assert conversations.rows[0]["status"] == "waiting"
    assert conversations.rows[0]["handoff_reason"] == "customer_requested_human"


def test_status_updates_only_the_matching_ycloud_message_and_never_regresses():
    channels = _Channels([{
        "id": "pilot", "type": "whatsapp", "provider": "ycloud", "connected": True,
        "workspace_id": "workspace-a", "waba_id": "waba-1", "display_phone": "+5543996676633",
    }])
    conversations, messages = _Conversations(), _Messages()
    conversations.criar({"canal_id": "pilot", "external_thread_id": "+5511999999999"}, "workspace-a")
    messages.criar({"conversa_id": "conv-1", "external_id": "ycloud:out-1", "provider_status": "sent"})
    service = _service(channels, conversations, messages)

    read = service.process_event({"type": "whatsapp.message.updated",
                                  "whatsappMessage": {"id": "out-1", "status": "read"}})
    stale = service.process_event({"type": "whatsapp.message.updated",
                                   "whatsappMessage": {"id": "out-1", "status": "delivered"}})
    late_failure = service.process_event({"type": "whatsapp.message.updated",
                                          "whatsappMessage": {"id": "out-1", "status": "failed"}})

    assert read["processed"] == 1
    assert stale["processed"] == 0
    assert late_failure["processed"] == 0
    assert messages.rows[0]["provider_status"] == "read"


def test_bot_turn_rechecks_human_state_and_marks_unanswered_for_human():
    channels = _Channels([{"id": "pilot", "provider": "ycloud", "workspace_id": "workspace-a"}])
    conversations, messages = _Conversations(), _Messages()
    row = conversations.criar({"canal_id": "pilot", "status": "active", "bot_activated": True,
                               "assigned_to": None}, "workspace-a")
    calls = []
    service = _service(channels, conversations, messages,
                       bot_handler=lambda *args: calls.append(args) or None)

    row["assigned_to"] = "agent-1"
    assert service.reply_if_eligible("conv-1", "Olá", "workspace-a") is False
    assert calls == []
    row["assigned_to"] = None
    assert service.reply_if_eligible("conv-1", "Olá", "workspace-a") is False
    assert calls == [("conv-1", "Olá", "whatsapp")]
    assert row["status"] == "waiting"
    assert row["handoff_reason"] == "bot_unavailable"


def test_channel_list_hides_other_workspace_pilot_and_keeps_legacy(monkeypatch):
    from app.services.platform_service import PlatformService

    service = PlatformService()
    service.repo = _Channels([
        {"id": "legacy", "type": "whatsapp", "name": "Meta", "connected": True,
         "provider": "meta", "messages_today": 3},
        {"id": "pilot-a", "type": "whatsapp", "name": "Piloto A", "connected": True,
         "provider": "ycloud", "workspace_id": "workspace-a", "messages_today": 1},
        {"id": "pilot-b", "type": "whatsapp", "name": "Piloto B", "connected": True,
         "provider": "ycloud", "workspace_id": "workspace-b", "messages_today": 2},
    ])
    monkeypatch.setattr(service, "_ensure_tables", lambda: None)
    monkeypatch.setattr(service, "_messages_today_by_channel_type", lambda: {"whatsapp": 7})

    result = service.get_channels("workspace-a")

    assert [row["id"] for row in result] == ["legacy", "pilot-a"]
    assert result[1]["messagesToday"] == 1


def test_generic_toggle_cannot_activate_unvalidated_ycloud(monkeypatch):
    from app.services.platform_service import PlatformService

    service = PlatformService()
    service.repo = _Channels([{
        "id": "pilot", "type": "whatsapp", "name": "Piloto", "connected": False,
        "provider": "ycloud", "workspace_id": "workspace-a",
    }])
    monkeypatch.setattr(service, "_ensure_tables", lambda: None)

    with pytest.raises(Exception) as error:
        service.toggle_channel("pilot")

    assert getattr(error.value, "status_code", None) == 409
    assert service.repo.rows[0]["connected"] is False


def test_ycloud_free_text_window_blocks_expired_and_missing_customer_timestamp():
    channels = _Channels([{"id": "pilot", "provider": "ycloud", "connected": True,
                           "workspace_id": "workspace-a", "waba_id": "waba-1",
                           "display_phone": "+5543996676633"}])
    service = _service(channels=channels)
    expired = (datetime.now(timezone.utc) - timedelta(hours=25)).isoformat()

    for value in (expired, None):
        with pytest.raises(Exception) as error:
            service.ensure_text_window({"last_customer_message_at": value})
        assert getattr(error.value, "status_code", None) == 409


def test_ycloud_send_uses_conversation_channel_and_returns_correlatable_id():
    channels = _Channels([{"id": "pilot", "provider": "ycloud", "connected": True,
                           "workspace_id": "workspace-a", "waba_id": "waba-1",
                           "display_phone": "+5543996676633"}])
    service = _service(channels=channels)
    sent = []
    service.provider.send_text = lambda to, body: sent.append((to, body)) or "out-2"
    conversation = {
        "id": "conv-1", "workspace_id": "workspace-a", "canal_id": "pilot",
        "contact_phone": "+5511999999999",
        "last_customer_message_at": datetime.now(timezone.utc).isoformat(),
    }

    result = service.send_for_conversation(conversation, "Olá cliente")

    assert result == {"sent": True, "provider": "ycloud", "providerStatus": "accepted",
                      "externalId": "ycloud:out-2"}
    assert sent == [("+5511999999999", "Olá cliente")]


def test_conversation_service_routes_pilot_before_workspace_fallback():
    from app.services.conversas_service import ConversasService

    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.usuarios = MagicMock()
    service.conversas.obter.return_value = {
        "id": "conv-1", "workspace_id": "workspace-a", "channel": "whatsapp",
        "provider": "ycloud", "canal_id": "pilot", "contact_phone": "+5511999999999",
        "last_customer_message_at": datetime.now(timezone.utc).isoformat(),
        "status": "active", "assigned_to": "user-1",
    }
    service.mensagens.criar.return_value = {"id": "message-1"}
    service.mensagens.atualizar.return_value = {"id": "message-1", "status": "sent",
                                                  "external_id": "ycloud:out-2"}
    service.mensagens.attach_ycloud_outbound.return_value = {
        "id": "message-1", "status": "sending", "provider_status": "accepted",
        "external_id": "ycloud:out-2",
    }
    with (
        patch("app.services.ycloud_service.ycloud_service") as ycloud,
        patch("app.services.xnamai_outbound_service.xnamai_outbound_service") as xnamai,
        patch("app.services.brevo_outbound_service.brevo_outbound_service") as brevo,
        patch("app.services.meta_instagram_outbound.is_meta_instagram", return_value=False),
        patch("app.services.human_takeover_bridge.mark_human_active"),
    ):
        ycloud.send_for_conversation.return_value = {
            "sent": True, "provider": "ycloud", "externalId": "ycloud:out-2",
        }
        service.enviar_mensagem("conv-1", "Olá cliente", workspace_id="workspace-a",
                                actor_user_id="user-1", actor_name="Ana")

    ycloud.send_for_conversation.assert_called_once()
    xnamai.enviar_para_conversa.assert_not_called()
    brevo.enviar_para_conversa.assert_not_called()
    assert service.mensagens.attach_ycloud_outbound.call_args.args == (
        "message-1", "ycloud:out-2", "workspace-a")


def test_ycloud_bot_can_resume_after_historical_human_message():
    from app.services.chatbot_service import ChatbotService

    service = ChatbotService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.platform = MagicMock()
    service.conversas_service = MagicMock()
    service.conversas.obter.return_value = {
        "id": "conv-1", "provider": "ycloud", "status": "active",
        "bot_activated": True, "assigned_to": None, "workspace_id": "workspace-a",
    }
    service.mensagens.listar_por_conversa.return_value = [
        {"sender": "agent", "content": "Resposta humana anterior"},
        {"sender": "customer", "content": "Nova dúvida"},
    ]
    service.platform.list_chatbots.return_value = [
        {"id": "flow-1", "channel": "whatsapp", "name": "Bot", "active": True},
    ]
    with patch("app.services.chatbot_service.agent_service.chat", return_value={"reply": "Resposta"}) as chat:
        result = service.handle_inbound("conv-1", "Nova dúvida", "whatsapp")

    assert result["reply"] == "Resposta"
    assert chat.call_args.kwargs["workspace_id"] == "workspace-a"
    service.conversas_service.enviar_mensagem.assert_called_once()


def test_ycloud_bot_drops_reply_if_human_assumes_during_generation():
    from app.services.chatbot_service import ChatbotService

    service = ChatbotService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.platform = MagicMock()
    service.conversas_service = MagicMock()
    row = {"id": "conv-1", "provider": "ycloud", "status": "active",
           "bot_activated": True, "assigned_to": None}
    service.conversas.obter.side_effect = lambda *_: dict(row)
    service.mensagens.listar_por_conversa.return_value = [{"sender": "customer", "content": "Oi"}]
    service.platform.list_chatbots.return_value = [
        {"id": "flow-1", "channel": "whatsapp", "name": "Bot", "active": True},
    ]

    def generate(*args, **kwargs):
        row["assigned_to"] = "agent-1"
        row["bot_activated"] = False
        return {"reply": "Resposta atrasada"}

    with patch("app.services.chatbot_service.agent_service.chat", side_effect=generate):
        result = service.handle_inbound("conv-1", "Oi", "whatsapp")

    assert result is None
    service.conversas_service.enviar_mensagem.assert_not_called()


def test_signed_webhook_rejects_invalid_signature_before_processing(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import ycloud as routes

    processed = []
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setattr(routes.ycloud_service, "process_event", lambda event: processed.append(event))
    app = FastAPI()
    app.include_router(routes.webhook_router)
    body = json.dumps(_inbound()).encode()

    response = TestClient(app).post("/webhooks/ycloud", content=body,
                                    headers={"YCloud-Signature": "t=1,s=" + "0" * 64})

    assert response.status_code == 401
    assert processed == []


def test_webhook_without_secret_fails_closed(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import ycloud as routes

    monkeypatch.delenv("YCLOUD_WEBHOOK_SECRET", raising=False)
    app = FastAPI()
    app.include_router(routes.webhook_router)

    response = TestClient(app).post("/webhooks/ycloud", json=_inbound())

    assert response.status_code == 503


def test_signed_webhook_accepts_valid_event(monkeypatch):
    from fastapi import FastAPI
    from fastapi.testclient import TestClient
    from app.routes import ycloud as routes

    body = json.dumps(_inbound()).encode()
    timestamp = int(__import__("time").time())
    digest = hmac.new(b"webhook-secret", str(timestamp).encode() + b"." + body, hashlib.sha256).hexdigest()
    seen = []
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "webhook-secret")
    monkeypatch.setattr(routes.ycloud_service, "process_event", lambda event: seen.append(event) or
                        {"processed": 1, "bot_jobs": []})
    app = FastAPI()
    app.include_router(routes.webhook_router)

    response = TestClient(app).post("/webhooks/ycloud", content=body,
                                    headers={"YCloud-Signature": f"t={timestamp},s={digest}"})

    assert response.status_code == 200
    assert response.json()["processed"] == 1
    assert seen[0]["type"] == "whatsapp.inbound_message.received"


def test_ycloud_contact_can_be_returned_to_bot_only_by_assignee():
    from app.services.contact_inbox_service import ContactInboxService

    service = ContactInboxService()
    service.repo = MagicMock()
    service.sessions = MagicMock()
    group = {"id": "group-1", "active_session_id": "conv-1",
             "session_ids": ["conv-1"], "last_message_at": "2026-10-23T12:00:00Z",
             "current_session": {"id": "conv-1", "provider": "ycloud",
                                 "assigned_to": "agent-1", "status": "active"}}
    service.obter = MagicMock(return_value=group)
    service.repo.atualizar_abertas.return_value = [{"id": "conv-1"}]
    with patch("app.services.contact_inbox_service.invalidate_conversa"):
        service.devolver_ao_bot("group-1", "workspace-a", "agent-1", "Ana")
    patch_data = service.repo.atualizar_abertas.call_args.args[2]
    assert service.repo.atualizar_abertas.call_args.kwargs["expected_assignee"] == "agent-1"
    assert patch_data["assigned_to"] is None
    assert patch_data["bot_activated"] is True
    assert patch_data["status"] == "active"
    assert patch_data["handoff_requested_at"] is None

    with pytest.raises(HTTPException) as error:
        service.devolver_ao_bot("group-1", "workspace-a", "agent-2", "Bia")
    assert error.value.status_code == 403


def test_ycloud_mapping_exposes_bot_state_and_window():
    from app.services.conversas_service import _map_conversa

    row = {"id": "conv-1", "provider": "ycloud", "status": "waiting",
           "handoff_requested_at": "2026-10-23T12:00:00Z", "handoff_reason": "bot_unavailable",
           "last_customer_message_at": "2026-10-23T11:00:00Z"}
    mapped = _map_conversa(row)
    assert mapped["handoffRequested"] is True
    assert mapped["botState"] == "waiting_human"
    assert mapped["lastCustomerMessageAt"] == row["last_customer_message_at"]


def test_ycloud_handoff_does_not_pause_legacy_agent_for_same_customer():
    from app.services.human_takeover_bridge import mark_human_active

    with patch("app.services.human_takeover_bridge.supabase") as database:
        mark_human_active({"provider": "ycloud", "contact_phone": "+5511999999999",
                           "external_thread_id": "+5511999999999"}, source="pilot")
    database.table.assert_not_called()


def test_channel_cannot_activate_without_webhook_secret(monkeypatch):
    from app.services.ycloud_service import YCloudService

    service = YCloudService(provider=MagicMock(), channels=_Channels())
    monkeypatch.delenv("YCLOUD_WEBHOOK_SECRET", raising=False)
    with pytest.raises(HTTPException) as error:
        service.connect("workspace-a", "Piloto")
    assert error.value.status_code == 503


def test_status_event_from_another_business_number_is_ignored():
    channels = _Channels([{"id": "pilot", "provider": "ycloud", "connected": True,
                           "workspace_id": "workspace-a", "waba_id": "waba-1",
                           "display_phone": "+5543996676633"}])
    conversations = _Conversations()
    conversations.rows.append({"id": "conv-1", "workspace_id": "workspace-a", "canal_id": "pilot"})
    messages = _Messages()
    messages.rows.append({"id": "msg-1", "conversa_id": "conv-1", "external_id": "ycloud:out-1",
                          "provider_status": "sent"})
    service = _service(channels=channels, conversations=conversations, messages=messages)
    assert not service.update_status({"id": "out-1", "status": "read", "from": "+5511999999999"})
    assert messages.rows[0]["provider_status"] == "sent"


def test_window_closing_during_send_marks_pending_message_failed():
    from app.services.conversas_service import ConversasService

    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.conversas.obter.return_value = {
        "id": "conv-1", "workspace_id": "workspace-a", "channel": "whatsapp",
        "provider": "ycloud", "canal_id": "pilot", "contact_phone": "+5511999999999",
        "last_customer_message_at": datetime.now(timezone.utc).isoformat(),
        "status": "active", "assigned_to": "agent-1",
    }
    service.mensagens.criar.return_value = {"id": "msg-1"}
    with patch("app.services.ycloud_service.ycloud_service") as ycloud:
        ycloud.send_for_conversation.side_effect = HTTPException(409, "Janela encerrada")
        with pytest.raises(HTTPException):
            service.enviar_mensagem("conv-1", "Olá", workspace_id="workspace-a",
                                    actor_user_id="agent-1", actor_name="Ana")
    assert service.mensagens.atualizar.call_args.args == (
        "msg-1", {"status": "failed", "provider_status": "failed"})


def test_ycloud_bot_requests_human_when_it_cannot_answer():
    from app.services.chatbot_service import ChatbotService

    service = ChatbotService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.platform = MagicMock()
    service.conversas_service = MagicMock()
    service.conversas.obter.return_value = {
        "id": "conv-1", "provider": "ycloud", "status": "active",
        "bot_activated": True, "assigned_to": None, "workspace_id": "workspace-a",
    }
    service.mensagens.listar_por_conversa.return_value = [{"sender": "customer", "content": "Dúvida difícil"}]
    service.platform.list_chatbots.return_value = [
        {"id": "flow-1", "channel": "whatsapp", "name": "Bot", "active": True},
    ]
    with patch("app.services.chatbot_service.agent_service.chat", return_value={
        "reply": "Não sei responder sua pergunta.", "source": "openai",
    }):
        result = service.handle_inbound("conv-1", "Dúvida difícil", "whatsapp")
    assert result["handoffRequested"] is True
    assert "atendente" in service.conversas_service.enviar_mensagem.call_args.args[1]
    assert service.conversas.atualizar.call_args.args[1]["handoff_reason"] == "bot_unavailable"


def test_ycloud_bot_reply_preserves_unread_customer_count():
    from app.services.conversas_service import ConversasService

    service = ConversasService()
    service.conversas = MagicMock()
    service.mensagens = MagicMock()
    service.conversas.obter.return_value = {
        "id": "conv-1", "workspace_id": "workspace-a", "channel": "whatsapp",
        "provider": "ycloud", "canal_id": "pilot", "contact_phone": "+5511999999999",
        "last_customer_message_at": datetime.now(timezone.utc).isoformat(),
        "status": "active", "assigned_to": None, "bot_activated": True, "unread_count": 2,
    }
    service.mensagens.criar.return_value = {"id": "msg-1"}
    with patch("app.services.ycloud_service.ycloud_service") as ycloud:
        ycloud.send_for_conversation.return_value = {"sent": True, "externalId": "ycloud:out-1"}
        service.enviar_mensagem("conv-1", "Resposta", sender="ai", workspace_id="workspace-a")
    assert "unread_count" not in service.conversas.atualizar.call_args.args[1]


def test_customer_denial_of_human_handoff_keeps_bot_active():
    channels = _Channels([{"id": "pilot", "provider": "ycloud", "connected": True,
                           "workspace_id": "workspace-a", "waba_id": "waba-1",
                           "display_phone": "+5543996676633"}])
    service = _service(channels=channels)
    event = _inbound()
    event["whatsappInboundMessage"]["text"]["body"] = "Não quero falar com atendente, responda aqui"
    with patch("app.services.inbox_cache.invalidate_conversa"):
        result = service.process_event(event)
    assert result["bot_jobs"]
    assert service.conversations.rows[0]["status"] == "active"


def test_status_does_not_reveal_pilot_number_to_another_workspace(monkeypatch):
    monkeypatch.setenv("YCLOUD_WEBHOOK_SECRET", "test-secret")
    channels = _Channels([{"id": "pilot", "provider": "ycloud", "connected": True,
                           "workspace_id": "workspace-a", "waba_id": "waba-1",
                           "display_phone": "+5543996676633"}])
    result = _service(channels=channels).status("workspace-b")
    assert result["phone"] is None
    assert result["configured"] is False


def test_early_status_is_reconciled_when_outbound_id_is_attached():
    channels = _Channels([{"id": "pilot", "provider": "ycloud", "connected": True,
                           "workspace_id": "workspace-a", "waba_id": "waba-1",
                           "display_phone": "+5543996676633"}])
    conversations, messages = _Conversations(), _Messages()
    service = _service(channels=channels, conversations=conversations, messages=messages)
    conversation = conversations.criar({"canal_id": "pilot", "provider": "ycloud"}, "workspace-a")

    assert service.update_status({"id": "out-1", "status": "delivered"})
    outbound = messages.criar({"conversa_id": conversation["id"], "status": "sending"})
    attached = messages.attach_ycloud_outbound(outbound["id"], "ycloud:out-1", "workspace-a")

    assert attached["provider_status"] == "delivered"
    assert attached["status"] == "delivered"


def test_inbound_repository_uses_atomic_database_function():
    from app.repositories.conversa_repository import ConversaRepository

    with patch("app.repositories.conversa_repository.supabase") as database:
        database.rpc.return_value.execute.return_value.data = {
            "inserted": True, "conversation_id": "conv-1", "should_reply": True,
        }
        result = ConversaRepository().ingest_ycloud_atomic(
            channel_id="pilot", workspace_id="workspace-a", external_id="ycloud:in-1",
            customer="+5511999999999", customer_name="Cliente", content="Oi",
            sent_at="2026-10-23T12:00:00Z", human_request=False,
        )

    assert result["inserted"] is True
    assert database.rpc.call_args.args[0] == "ycloud_ingest_inbound"
    assert database.rpc.call_args.args[1]["p_external_id"] == "ycloud:in-1"


def _history_event(direction, message_id, sent_at="2026-01-05T10:00:00Z"):
    base = {"id": message_id, "wabaId": "waba-1", "sendTime": sent_at,
            "type": "text", "text": {"body": "Mensagem antiga"}}
    if direction == "inbound":
        base.update({"from": "5511999999999", "to": "5543996676633",
                     "customerProfile": {"name": "Cliente Antigo"}})
        return {"type": "whatsapp.smb.history", "whatsappInboundMessage": base}
    base.update({"from": "5543996676633", "to": "5511999999999"})
    return {"type": "whatsapp.smb.history", "whatsappMessage": base}


_PILOT_ROW = {
    "id": "pilot", "type": "whatsapp", "provider": "ycloud", "connected": True,
    "workspace_id": "workspace-a", "waba_id": "waba-1", "display_phone": "+5543996676633",
}


def test_history_stores_both_directions_per_contact_without_side_effects():
    conversations, messages = _Conversations(), _Messages()
    service = _service(_Channels([dict(_PILOT_ROW)]), conversations, messages)

    first = service.process_event(_history_event("inbound", "h-1"))
    second = service.process_event(_history_event("outbound", "h-2"))
    repeat = service.process_event(_history_event("inbound", "h-1"))

    assert first == {"processed": 1, "bot_jobs": []}
    assert second == {"processed": 1, "bot_jobs": []}
    assert repeat == {"processed": 0, "bot_jobs": []}
    assert len(conversations.rows) == 1
    assert conversations.rows[0]["status"] == "closed"
    assert conversations.rows[0]["unread_count"] == 0
    assert [(m["sender"], m["direction"]) for m in messages.rows] == [
        ("customer", "inbound"), ("agent", "outbound")]


def test_history_ignores_other_business_number_and_progress_only_events():
    conversations, messages = _Conversations(), _Messages()
    service = _service(_Channels([dict(_PILOT_ROW)]), conversations, messages)
    other = _history_event("inbound", "h-3")
    other["whatsappInboundMessage"]["to"] = "5511888888888"

    assert service.process_event(other)["processed"] == 0
    assert service.process_event({"type": "whatsapp.smb.history", "phase": 0, "progress": 10})["processed"] == 0
    assert conversations.rows == [] and messages.rows == []
