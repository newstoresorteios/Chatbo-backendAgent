import logging
import re
import uuid
from datetime import datetime

from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.repositories.platform_repository import PlatformRepository
from app.services.agent_service import agent_service
from app.services.conversas_service import ConversasService

logger = logging.getLogger(__name__)

RESOLVED_PATTERN = re.compile(
    r"\b(obrigad[oa]|valeu|resolvido|perfeito|at[eé]\s+mais|pode\s+encerrar)\b",
    re.I,
)


class ChatbotService:

    def __init__(self):
        self.conversas = ConversaRepository()
        self.mensagens = MensagemRepository()
        self.platform = PlatformRepository()
        self.conversas_service = ConversasService()

    def _human_agent_active(self, messages: list[dict]) -> bool:
        for msg in messages:
            if msg.get("sender") != "agent":
                continue
            content = (msg.get("content") or "").strip()
            if content and not content.startswith("[Sistema]"):
                return True
        return False

    def _active_flow(self, channel: str) -> dict | None:
        for row in self.platform.list_chatbots():
            if row.get("channel") == channel and row.get("active") is not False:
                return row
        return None

    def _build_history(self, messages: list[dict]) -> list[dict]:
        history: list[dict] = []
        for msg in messages[-16:]:
            sender = msg.get("sender") or "user"
            role = "assistant" if sender in {"agent", "ai"} else "user"
            content = msg.get("content") or ""
            if content:
                history.append({"role": role, "content": content})
        return history

    def _update_metrics(self, conversa: dict, flow: dict, *, resolved: bool = False) -> None:
        flow_id = str(flow["id"])
        conversa_id = str(conversa["id"])
        triggers_delta = 0
        resolved_delta = 0

        if not conversa.get("bot_activated"):
            triggers_delta = 1
            self.conversas.atualizar(conversa_id, {
                "bot_flow_id": flow_id,
                "bot_activated": True,
            })

        if resolved:
            resolved_delta = 1

        if triggers_delta or resolved_delta:
            self.platform.increment_chatbot_stats(flow_id, triggers_delta, resolved_delta)

    def handle_inbound(
        self,
        conversa_id: str,
        message: str,
        channel: str,
        *,
        flow_id: str | None = None,
    ) -> dict | None:
        conversa = self.conversas.obter(conversa_id)
        if not conversa:
            return None

        if conversa.get("status") == "closed":
            return None

        if conversa.get("assigned_to"):
            return None

        messages = self.mensagens.listar_por_conversa(conversa_id)
        if self._human_agent_active(messages):
            return None

        flow = self.platform.get_chatbot(flow_id) if flow_id else self._active_flow(channel)
        if not flow or flow.get("active") is False:
            return None

        if flow.get("channel") and flow["channel"] != channel:
            return None

        history = self._build_history(messages)
        prompt = (
            f"Fluxo ativo: {flow.get('name')}. "
            "Responda ao CLIENTE final (nao ao atendente). "
            "Seja breve, cordial e objetivo para WhatsApp. "
            f"Mensagem do cliente: {message.strip()}"
        )

        try:
            result = agent_service.chat(
                prompt,
                conversation_id=conversa_id,
                customer_id=str(conversa.get("cliente_mercos_id") or "") or None,
                mode="agent",
                history=history,
            )
        except Exception as exc:
            logger.warning("Chatbot IA falhou (%s): %s", conversa_id, exc)
            return None

        reply = (result.get("reply") or "").strip()
        if not reply:
            return None

        try:
            self.conversas_service.enviar_mensagem(conversa_id, reply, sender="ai")
        except Exception as exc:
            logger.warning("Chatbot nao enviou resposta (%s): %s", conversa_id, exc)
            return None

        resolved = bool(RESOLVED_PATTERN.search(message))
        self._update_metrics(conversa, flow, resolved=resolved)

        return {
            "conversationId": conversa_id,
            "flowId": str(flow["id"]),
            "flowName": flow.get("name"),
            "reply": reply,
            "source": result.get("source", "intelligent"),
            "resolved": resolved,
        }

    def test_flow(
        self,
        flow_id: str,
        *,
        conversation_id: str | None = None,
        message: str | None = None,
    ) -> dict:
        flow = self.platform.get_chatbot(flow_id)
        if not flow:
            raise ValueError("Fluxo não encontrado")

        channel = flow.get("channel") or "whatsapp"
        test_message = (message or "Olá, preciso de ajuda").strip()

        conversa = None
        if conversation_id:
            conversa = self.conversas.obter(conversation_id)

        # Teste sempre usa conversa nova, sem atendente humano (reuso quebrava com assigned_to)
        if not conversa:
            conversa = self.conversas.criar({
                "customer_name": "Cliente Teste Robô",
                "channel": channel,
                "status": "active",
                "unread_count": 0,
                "last_message": test_message,
                "last_message_at": datetime.utcnow().isoformat(),
                "protocol": f"PD-TEST-{uuid.uuid4().hex[:6].upper()}",
            })

        conversa_id = str(conversa["id"])

        self.mensagens.criar({
            "conversa_id": conversa_id,
            "content": test_message,
            "sender": "customer",
            "status": "delivered",
        })
        self.conversas.atualizar(conversa_id, {
            "last_message": test_message,
            "last_message_at": conversa.get("last_message_at"),
            "status": "active",
        })

        result = self.handle_inbound(
            conversa_id,
            test_message,
            channel,
            flow_id=flow_id,
        )

        if not result:
            return {
                "success": False,
                "conversationId": conversa_id,
                "message": "Robô não respondeu. Verifique se o fluxo está ativo e se há atendente humano na conversa.",
            }

        return {
            "success": True,
            "conversationId": conversa_id,
            "reply": result.get("reply"),
            "source": result.get("source"),
            "flowName": result.get("flowName"),
        }


chatbot_service = ChatbotService()
