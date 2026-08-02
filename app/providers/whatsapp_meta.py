import hashlib
import hmac
import logging

import requests

from app.config.settings import (
    META_ACCESS_TOKEN,
    META_API_VERSION,
    META_APP_SECRET,
    META_PHONE_NUMBER_ID,
)

logger = logging.getLogger(__name__)


def whatsapp_meta_configurado() -> bool:
    return bool(META_ACCESS_TOKEN and META_PHONE_NUMBER_ID)


class WhatsAppMetaProvider:

    def __init__(
        self,
        *,
        access_token: str | None = None,
        phone_number_id: str | None = None,
    ):
        self.access_token = access_token or META_ACCESS_TOKEN
        self.phone_number_id = phone_number_id or META_PHONE_NUMBER_ID
        self.api_version = META_API_VERSION

    def _base_url(self) -> str:
        return f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}"

    def configurado(self) -> bool:
        return bool(self.access_token and self.phone_number_id)

    def verificar_assinatura(self, payload: bytes, signature_header: str | None) -> bool:
        if not META_APP_SECRET:
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        expected = hmac.new(
            META_APP_SECRET.encode(),
            payload,
            hashlib.sha256,
        ).hexdigest()
        received = signature_header.removeprefix("sha256=")
        return hmac.compare_digest(expected, received)

    def enviar_texto(self, to_phone: str, body: str) -> dict:
        if not self.configurado():
            raise RuntimeError(
                "WhatsApp Meta não configurado. Defina META_ACCESS_TOKEN e META_PHONE_NUMBER_ID no Render."
            )

        numero = "".join(ch for ch in to_phone if ch.isdigit())
        if not numero:
            raise ValueError("Número de telefone inválido")

        response = requests.post(
            f"{self._base_url()}/messages",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "to": numero,
                "type": "text",
                "text": {"body": body[:4096]},
            },
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def testar_conexao(self) -> dict:
        if not self.configurado():
            return {"ok": False, "message": "Credenciais Meta não configuradas no servidor"}

        response = requests.get(
            f"https://graph.facebook.com/{self.api_version}/{self.phone_number_id}",
            headers={"Authorization": f"Bearer {self.access_token}"},
            timeout=30,
        )
        if response.status_code != 200:
            detail = response.text[:200]
            return {"ok": False, "message": f"Meta API respondeu {response.status_code}: {detail}"}

        data = response.json()
        display = data.get("display_phone_number") or data.get("verified_name") or self.phone_number_id
        return {
            "ok": True,
            "message": f"WhatsApp conectado ({display})",
            "displayPhone": display,
        }
