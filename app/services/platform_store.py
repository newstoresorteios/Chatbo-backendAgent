from copy import deepcopy
from datetime import datetime
import uuid

from app.data.platform_seed import (
    SEED_CAMPAIGNS,
    SEED_CHANNELS,
    SEED_CHATBOTS,
    SEED_CONVERSATIONS,
    SEED_FUNNEL,
    SEED_INTEGRATIONS,
    SEED_MESSAGES,
)


def _now() -> str:
    return datetime.utcnow().isoformat()


class PlatformStore:
    def __init__(self):
        self.channels = deepcopy(SEED_CHANNELS)
        self.integrations = deepcopy(SEED_INTEGRATIONS)
        self.campaigns = deepcopy(SEED_CAMPAIGNS)
        self.chatbots = deepcopy(SEED_CHATBOTS)
        self.funnel = deepcopy(SEED_FUNNEL)
        self.conversations = deepcopy(SEED_CONVERSATIONS)
        self.messages = deepcopy(SEED_MESSAGES)

    # Canais
    def get_channels(self):
        return self.channels

    def connect_channel(self, channel_type: str, name: str):
        channel = {
            "id": f"ch-{uuid.uuid4().hex[:8]}",
            "type": channel_type,
            "name": name,
            "connected": True,
            "messagesToday": 0,
            "lastActivity": _now(),
        }
        self.channels.append(channel)
        return channel

    def update_channel(self, channel_id: str, patch: dict):
        for channel in self.channels:
            if channel["id"] == channel_id:
                channel.update(patch)
                return channel
        return None

    def toggle_channel(self, channel_id: str):
        for channel in self.channels:
            if channel["id"] == channel_id:
                channel["connected"] = not channel["connected"]
                channel["lastActivity"] = _now()
                return channel
        return None

    # Integrações
    def get_integrations(self):
        return self.integrations

    def toggle_integration(self, integration_id: str):
        for item in self.integrations:
            if item["id"] == integration_id:
                item["connected"] = not item["connected"]
                return item
        return None

    # Campanhas
    def get_campaigns(self):
        return self.campaigns

    def add_campaign(self, campaign: dict):
        item = {
            **campaign,
            "id": f"cp-{uuid.uuid4().hex[:8]}",
            "sent": 0,
            "opened": 0,
        }
        self.campaigns.insert(0, item)
        return item

    # Chatbot
    def get_chatbots(self):
        return self.chatbots

    def add_chatbot(self, flow: dict):
        item = {
            **flow,
            "id": f"bot-{uuid.uuid4().hex[:8]}",
            "triggers": 0,
            "resolved": 0,
        }
        self.chatbots.insert(0, item)
        return item

    def toggle_chatbot(self, flow_id: str):
        for item in self.chatbots:
            if item["id"] == flow_id:
                item["active"] = not item["active"]
                return item
        return None

    def update_chatbot(self, flow_id: str, patch: dict):
        for item in self.chatbots:
            if item["id"] == flow_id:
                item.update(patch)
                return item
        return None

    # Funil
    def get_funnel(self):
        return self.funnel

    def move_deal(self, deal_id: str, stage_id: str):
        deal = None
        source_stage = None

        for stage in self.funnel:
            for item in stage["deals"]:
                if item["id"] == deal_id:
                    deal = item
                    source_stage = stage
                    break
            if deal:
                break

        if not deal or not source_stage:
            return False

        source_stage["deals"] = [d for d in source_stage["deals"] if d["id"] != deal_id]

        for stage in self.funnel:
            if stage["id"] == stage_id:
                deal["stageId"] = stage_id
                stage["deals"].append(deal)
                return True

        return False

    # Conversas
    def get_conversations(self):
        return self.conversations

    def get_messages(self, conversation_id: str):
        return self.messages.get(conversation_id, [])

    def send_message(self, conversation_id: str, content: str, sender: str = "agent"):
        message = {
            "id": f"m-{uuid.uuid4().hex[:8]}",
            "conversationId": conversation_id,
            "content": content,
            "sender": sender,
            "timestamp": _now(),
            "status": "sent",
        }
        self.messages.setdefault(conversation_id, []).append(message)
        for conv in self.conversations:
            if conv["id"] == conversation_id:
                conv["lastMessage"] = content
                conv["lastMessageAt"] = message["timestamp"]
                break
        return message


platform_store = PlatformStore()
