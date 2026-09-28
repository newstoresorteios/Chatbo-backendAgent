from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentInboundEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    provider: Literal["ycloud", "brevo", "meta"]
    message_id: str = Field(alias="messageId", min_length=1, max_length=255)
    event_type: str | None = Field(default=None, alias="eventType", max_length=255)
    conversation_id: str | None = Field(default=None, alias="conversationId", max_length=500)
    channel: str = Field(default="whatsapp", min_length=1, max_length=50)
    sender_key: str | None = Field(default=None, alias="senderKey", max_length=500)
    sender_external_id: str | None = Field(default=None, alias="senderExternalId", max_length=500)
    visitor_id: str | None = Field(default=None, alias="visitorId", max_length=500)
    sender_username: str | None = Field(default=None, alias="senderUsername", max_length=255)
    source_channel_ref: str | None = Field(default=None, alias="sourceChannelRef", max_length=500)
    source_channel_link: str | None = Field(default=None, alias="sourceChannelLink", max_length=1000)
    source_conversation_ref: str | None = Field(default=None, alias="sourceConversationRef", max_length=500)
    sender_phone: str | None = Field(default=None, alias="senderPhone", max_length=50)
    sender_name: str | None = Field(default=None, alias="senderName", max_length=255)
    text: str = Field(default="", max_length=50000)
    channel_metadata: dict[str, Any] = Field(default_factory=dict, alias="channelMetadata")
    created_at: datetime | None = Field(default=None, alias="createdAt")


class AgentResponseEvent(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    reply_text: str = Field(alias="replyText", min_length=1, max_length=50000)
    intent: str | None = Field(default=None, max_length=255)
    handoff_required: bool = Field(default=False, alias="handoffRequired")
    safety_reason: str | None = Field(default=None, alias="safetyReason", max_length=1000)
    provider_send_ok: bool = Field(default=False, alias="providerSendOk")
    provider_response: dict[str, Any] = Field(default_factory=dict, alias="providerResponse")
    created_at: datetime | None = Field(default=None, alias="createdAt")


class AgentConversationTurn(BaseModel):
    inbound: AgentInboundEvent
    response: AgentResponseEvent | None = None
