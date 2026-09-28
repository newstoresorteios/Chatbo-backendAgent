from __future__ import annotations

from fastapi import HTTPException
import pytest

from app.schemas.agent_conversation_ingest import AgentConversationTurn
from app.services.agent_conversation_ingest_service import AgentConversationIngestService


WORKSPACE = "aa774d20-509f-4d54-865b-7a5de22b6d30"


class FakeWorkspaceRepository:
    def buscar_workspace(self, workspace_id: str):
        return {"id": workspace_id, "status": "active"}


class FakeRepository:
    def __init__(self):
        self.inbound = None
        self.response = None

    def find_inbound(self, provider, message_id):
        return self.inbound

    def insert_inbound(self, payload):
        self.inbound = {"id": 41, **payload}
        return self.inbound

    def find_response(self, workspace_id, source_event_key):
        return self.response

    def insert_response(self, payload):
        self.response = {"id": 87, **payload}
        return self.response


class FakeBridge:
    def __init__(self):
        self.events = []

    def sync_event(self, table, row):
        self.events.append((table, row))


def turn():
    return AgentConversationTurn.model_validate(
        {
            "inbound": {
                "provider": "ycloud",
                "messageId": "wamid.in-1",
                "conversationId": "wa:5511999999999",
                "channel": "whatsapp",
                "senderKey": "whatsapp:5511999999999",
                "senderPhone": "5511999999999",
                "senderName": "Cliente",
                "text": "Olá",
                "channelMetadata": {"ycloud_to": "5511955575530"},
            },
            "response": {
                "replyText": "Oi! Como posso ajudar?",
                "intent": "greeting",
                "providerSendOk": True,
                "providerResponse": {"provider": "ycloud"},
            },
        }
    )


def service(repository=None):
    repository = repository or FakeRepository()
    bridge = FakeBridge()
    return (
        AgentConversationIngestService(repository, FakeWorkspaceRepository(), bridge),
        repository,
        bridge,
    )


def test_ingest_stamps_workspace_on_inbound_and_response():
    ingest, repository, bridge = service()

    result = ingest.ingest_turn(WORKSPACE, turn())

    assert repository.inbound["workspace_id"] == WORKSPACE
    assert repository.response["workspace_id"] == WORKSPACE
    assert repository.response["inbound_id"] == 41
    assert repository.response["source_event_key"] == "ycloud:wamid.in-1:agent"
    assert result["inboundCreated"] is True
    assert result["responseCreated"] is True
    assert [event[0] for event in bridge.events] == [
        "ai_inbound_messages",
        "ai_agent_responses",
    ]


def test_ingest_is_idempotent_for_same_provider_message():
    ingest, repository, _ = service()
    first = ingest.ingest_turn(WORKSPACE, turn())
    second = ingest.ingest_turn(WORKSPACE, turn())

    assert first["inboundId"] == second["inboundId"] == 41
    assert second["inboundCreated"] is False
    assert second["responseCreated"] is False


def test_existing_message_cannot_be_reassigned_to_another_workspace():
    repository = FakeRepository()
    repository.inbound = {
        "id": 41,
        "provider": "ycloud",
        "message_id": "wamid.in-1",
        "workspace_id": "b3d7eed2-1cd0-45ac-82c7-8a8e8c0430b8",
    }
    ingest, _, _ = service(repository)

    with pytest.raises(HTTPException) as error:
        ingest.ingest_turn(WORKSPACE, turn())

    assert error.value.status_code == 409


def test_concurrent_duplicate_is_recovered_as_idempotent():
    class ConcurrentRepository(FakeRepository):
        def insert_inbound(self, payload):
            self.inbound = {"id": 42, **payload}
            raise RuntimeError("duplicate key")

        def insert_response(self, payload):
            self.response = {"id": 88, **payload}
            raise RuntimeError("duplicate key")

    ingest, _, _ = service(ConcurrentRepository())

    result = ingest.ingest_turn(WORKSPACE, turn())

    assert result["inboundId"] == 42
    assert result["responseId"] == 88
    assert result["inboundCreated"] is False
    assert result["responseCreated"] is False
