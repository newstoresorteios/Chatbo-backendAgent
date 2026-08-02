import logging
import uuid
from datetime import datetime

from fastapi import HTTPException

from app.config.settings import (
    META_ACCESS_TOKEN,
    META_PHONE_NUMBER_ID,
    META_WEBHOOK_VERIFY_TOKEN,
    PUBLIC_API_URL,
)
from app.providers.whatsapp_meta import WhatsAppMetaProvider, whatsapp_meta_configurado
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.repositories.platform_repository import PlatformRepository

logger = logging.getLogger(__name__)


def _mask(value: str | None, visible: int = 4) -> str | None:
    if not value:
        return None
    if len(value) <= visible:
        return "*" * len(value)
    return f"{'*' * (len(value) - visible)}{value[-visible:]}"


class WhatsAppService:

    def __init__(self):
        self.canais = PlatformRepository()
        self.conversas = ConversaRepository()
        self.mensagens = MensagemRepository()

    def _provider_for_canal(self, canal: dict | None) -> WhatsAppMetaProvider:
        token = (canal or {}).get("access_token") or META_ACCESS_TOKEN
        phone_id = (canal or {}).get("phone_number_id") or META_PHONE_NUMBER_ID
        return WhatsAppMetaProvider(access_token=token, phone_number_id=phone_id)

    def _resolve_canal(self, phone_number_id: str | None = None) -> dict | None:
        if phone_number_id:
            canal = self.canais.get_canal_by_phone_number_id(phone_number_id)
            if canal:
                return canal

        canais = self.canais.list_canais()
        whatsapp = [c for c in canais if c.get("type") == "whatsapp"]
        if not whatsapp:
            return None

        active = [c for c in whatsapp if c.get("provider_status") == "active" or c.get("connected")]
        return (active or whatsapp)[0]

    def status(self) -> dict:
        canal = self._resolve_canal(META_PHONE_NUMBER_ID)
        provider = self._provider_for_canal(canal)
        test = provider.testar_conexao() if provider.configurado() else {"ok": False, "message": "Não configurado"}

        return {
            "configured": provider.configurado(),
            "connected": bool(test.get("ok")),
            "provider": "meta",
            "webhookUrl": f"{PUBLIC_API_URL.rstrip('/')}/webhooks/whatsapp",
            "phoneNumberId": _mask(canal.get("phone_number_id") if canal else META_PHONE_NUMBER_ID),
            "displayPhone": canal.get("display_phone") if canal else test.get("displayPhone"),
            "canalId": canal.get("id") if canal else None,
            "providerStatus": (canal or {}).get("provider_status") or ("active" if test.get("ok") else "pending"),
            "message": test.get("message"),
        }

    def conectar_canal(
        self,
        *,
        name: str,
        phone_number_id: str | None = None,
        access_token: str | None = None,
        display_phone: str | None = None,
        waba_id: str | None = None,
    ) -> dict:
        phone_id = phone_number_id or META_PHONE_NUMBER_ID
        token = access_token or META_ACCESS_TOKEN
        provider = WhatsAppMetaProvider(access_token=token, phone_number_id=phone_id)
        test = provider.testar_conexao() if provider.configurado() else {"ok": False}

        canal_existente = self._resolve_canal(phone_id)
        dados = {
            "type": "whatsapp",
            "name": name.strip(),
            "provider": "meta",
            "provider_status": "active" if test.get("ok") else "pending",
            "connected": bool(test.get("ok")),
            "phone_number_id": phone_id,
            "access_token": token,
            "display_phone": display_phone or test.get("displayPhone"),
            "waba_id": waba_id,
            "last_activity": datetime.utcnow().isoformat(),
        }

        if canal_existente:
            row = self.canais.update_canal(canal_existente["id"], dados)
        else:
            dados["id"] = f"ch-wa-{uuid.uuid4().hex[:8]}"
            dados["messages_today"] = 0
            row = self.canais.create_canal(dados)

        return self._map_canal_publico(row or dados)

    def testar_conexao(self) -> dict:
        canal = self._resolve_canal()
        provider = self._provider_for_canal(canal)
        result = provider.testar_conexao()
        if result.get("ok") and canal:
            self.canais.update_canal(canal["id"], {
                "connected": True,
                "provider_status": "active",
                "display_phone": result.get("displayPhone") or canal.get("display_phone"),
                "last_activity": datetime.utcnow().isoformat(),
            })
        return result

    def verificar_webhook(self, mode: str | None, token: str | None, challenge: str | None) -> str:
        if mode == "subscribe" and token == META_WEBHOOK_VERIFY_TOKEN:
            return challenge or ""
        raise HTTPException(status_code=403, detail="Verificação do webhook falhou")

    def processar_webhook(self, payload: dict) -> dict:
        if payload.get("object") != "whatsapp_business_account":
            return {"processed": 0}

        processed = 0
        for entry in payload.get("entry") or []:
            for change in entry.get("changes") or []:
                value = change.get("value") or {}
                metadata = value.get("metadata") or {}
                phone_number_id = metadata.get("phone_number_id")
                canal = self._resolve_canal(phone_number_id)
                if not canal:
                    logger.warning("Webhook WhatsApp sem canal para phone_number_id=%s", phone_number_id)
                    continue

                contacts = {
                    c.get("wa_id"): (c.get("profile") or {}).get("name")
                    for c in (value.get("contacts") or [])
                }

                for message in value.get("messages") or []:
                    if self._processar_mensagem_inbound(canal, message, contacts):
                        processed += 1

                for status in value.get("statuses") or []:
                    self._processar_status(status)

        if canal := self._resolve_canal():
            self.canais.update_canal(canal["id"], {
                "last_activity": datetime.utcnow().isoformat(),
            })

        return {"processed": processed}

    def _processar_mensagem_inbound(
        self,
        canal: dict,
        message: dict,
        contacts: dict[str, str | None],
    ) -> bool:
        external_id = message.get("id")
        if external_id and self.mensagens.existe_external_id(external_id):
            return False

        wa_id = str(message.get("from") or "")
        if not wa_id:
            return False

        content = self._extrair_conteudo(message)
        if not content:
            return False

        conversa = self.conversas.obter_por_thread(str(canal["id"]), wa_id)
        customer_name = contacts.get(wa_id) or f"WhatsApp {wa_id[-4:]}"

        if not conversa:
            conversa = self.conversas.criar({
                "canal_id": str(canal["id"]),
                "external_thread_id": wa_id,
                "contact_phone": wa_id,
                "customer_name": customer_name,
                "channel": "whatsapp",
                "status": "active",
                "unread_count": 1,
                "last_message": content,
                "last_message_at": datetime.utcnow().isoformat(),
                "protocol": f"PD-{datetime.utcnow().strftime('%Y%m%d')}-{wa_id[-4:]}",
            })
        else:
            unread = int(conversa.get("unread_count") or 0) + 1
            self.conversas.atualizar(str(conversa["id"]), {
                "customer_name": customer_name,
                "unread_count": unread,
                "last_message": content,
                "last_message_at": datetime.utcnow().isoformat(),
                "status": "active",
            })

        self.mensagens.criar({
            "conversa_id": str(conversa["id"]),
            "content": content,
            "sender": "customer",
            "status": "delivered",
            "direction": "inbound",
            "external_id": external_id,
            "provider_status": "received",
        })

        try:
            from app.services.chatbot_service import chatbot_service

            chatbot_service.handle_inbound(str(conversa["id"]), content, "whatsapp")
        except Exception as exc:
            logger.warning("Chatbot runtime falhou no WhatsApp: %s", exc)

        return True

    def _processar_status(self, status: dict) -> None:
        external_id = status.get("id")
        if not external_id:
            return
        provider_status = status.get("status")
        if provider_status:
            self.mensagens.atualizar_por_external_id(external_id, {"provider_status": provider_status})

    def _extrair_conteudo(self, message: dict) -> str:
        msg_type = message.get("type")
        if msg_type == "text":
            return (message.get("text") or {}).get("body") or ""
        if msg_type == "button":
            return (message.get("button") or {}).get("text") or ""
        if msg_type == "interactive":
            interactive = message.get("interactive") or {}
            if interactive.get("type") == "button_reply":
                return (interactive.get("button_reply") or {}).get("title") or ""
            if interactive.get("type") == "list_reply":
                return (interactive.get("list_reply") or {}).get("title") or ""
        return f"[{msg_type or 'mensagem'} recebida]"

    def enviar_para_conversa(self, conversa: dict, content: str, mensagem_id: str | None = None) -> dict:
        phone = conversa.get("contact_phone") or conversa.get("external_thread_id")
        if not phone:
            return {"sent": False, "reason": "Conversa sem telefone"}

        canal = None
        if conversa.get("canal_id"):
            canal = self.canais.get_canal(str(conversa["canal_id"]))
        canal = canal or self._resolve_canal()

        provider = self._provider_for_canal(canal)
        if not provider.configurado() or not (canal or {}).get("connected", True):
            return {"sent": False, "reason": "WhatsApp não conectado"}

        try:
            resposta = provider.enviar_texto(str(phone), content)
        except Exception as exc:
            logger.exception("Falha ao enviar WhatsApp: %s", exc)
            if mensagem_id:
                self.mensagens.atualizar(mensagem_id, {
                    "status": "failed",
                    "provider_status": "failed",
                })
            return {"sent": False, "reason": str(exc)}

        messages = (resposta.get("messages") or [{}])
        external_id = messages[0].get("id")
        if mensagem_id and external_id:
            self.mensagens.atualizar(mensagem_id, {
                "external_id": external_id,
                "provider_status": "sent",
                "status": "sent",
            })

        if canal:
            self.canais.update_canal(canal["id"], {
                "last_activity": datetime.utcnow().isoformat(),
            })

        return {"sent": True, "externalId": external_id}

    def _map_canal_publico(self, row: dict) -> dict:
        return {
            "id": str(row["id"]),
            "type": row["type"],
            "name": row["name"],
            "connected": bool(row.get("connected")),
            "provider": row.get("provider") or "meta",
            "providerStatus": row.get("provider_status") or "pending",
            "phoneNumberId": _mask(row.get("phone_number_id")),
            "displayPhone": row.get("display_phone") or row.get("phone"),
            "phone": row.get("display_phone") or row.get("phone"),
        }


whatsapp_service = WhatsAppService()
