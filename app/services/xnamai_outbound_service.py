import logging

import requests

from app.config.settings import (
    XNAMAI_AGENT_TOKEN,
    XNAMAI_AGENT_URL,
    XNAMAI_WORKSPACE_ID,
)


logger = logging.getLogger(__name__)


class XNamaiOutboundService:
    def is_workspace(self, workspace_id: str | None) -> bool:
        return bool(workspace_id) and str(workspace_id) == XNAMAI_WORKSPACE_ID

    def configurado(self) -> bool:
        return bool(XNAMAI_AGENT_URL and XNAMAI_AGENT_TOKEN)

    def enviar_para_conversa(
        self,
        conversa: dict,
        content: str,
        *,
        correlation_id: str | None = None,
    ) -> dict:
        if not self.configurado():
            return {
                "sent": False,
                "reason": (
                    "Canal YCloud da XNamai não configurado no backend: "
                    "defina XNAMAI_AGENT_TOKEN no Render."
                ),
            }

        recipient = str(conversa.get("contact_phone") or "").strip()
        if not recipient:
            return {"sent": False, "reason": "Telefone do contato XNamai ausente"}

        url = f"{XNAMAI_AGENT_URL.rstrip('/')}/api/internal/chatbo/outbound"
        payload = {
            "workspaceId": XNAMAI_WORKSPACE_ID,
            "recipient": recipient,
            "content": content,
            "correlationId": correlation_id,
        }
        try:
            response = requests.post(
                url,
                json=payload,
                headers={
                    "Authorization": f"Bearer {XNAMAI_AGENT_TOKEN}",
                    "Accept": "application/json",
                },
                timeout=25,
            )
        except requests.RequestException as exc:
            logger.exception("Falha ao chamar runtime YCloud da XNamai")
            return {
                "sent": False,
                "reason": f"YCloud XNamai indisponível: {type(exc).__name__}",
            }

        try:
            data = response.json()
        except ValueError:
            data = {}
        if response.ok and data.get("ok"):
            return {
                "sent": True,
                "provider": "ycloud",
                "providerMessageId": data.get("provider_message_id") or data.get("wamid"),
            }

        detail = data.get("detail") or data.get("error") or "falha no envio"
        return {
            "sent": False,
            "reason": f"YCloud XNamai HTTP {response.status_code}: {detail}",
            "provider": "ycloud",
        }


xnamai_outbound_service = XNamaiOutboundService()
