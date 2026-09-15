import hashlib
import hmac
import logging
from urllib.parse import urlparse

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

    def marcar_lida(self, message_id: str) -> dict:
        if not self.configurado():
            raise RuntimeError("WhatsApp Meta não configurado")
        if not message_id.startswith("wamid."):
            raise ValueError("ID de mensagem WhatsApp inválido")
        response = requests.put(
            f"{self._base_url()}/messages",
            headers={
                "Authorization": f"Bearer {self.access_token}",
                "Content-Type": "application/json",
            },
            json={
                "messaging_product": "whatsapp",
                "status": "read",
                "message_id": message_id,
            },
            timeout=10,
        )
        response.raise_for_status()
        return response.json()

    def upload_media(self, filename: str, content: bytes, content_type: str) -> str:
        response = requests.post(
            f"{self._base_url()}/media",
            headers={"Authorization": f"Bearer {self.access_token}"},
            data={"messaging_product": "whatsapp"},
            files={"file": (filename, content, content_type)},
            timeout=60,
        )
        response.raise_for_status()
        return str(response.json()["id"])

    def enviar_media(self, to_phone: str, kind: str, media_id: str,
                     filename: str, caption: str = "") -> dict:
        media = {"id": media_id}
        if kind == "document":
            media["filename"] = filename
        if caption and kind in {"image", "document"}:
            media["caption"] = caption[:1024]
        response = requests.post(
            f"{self._base_url()}/messages",
            headers={"Authorization": f"Bearer {self.access_token}"},
            json={"messaging_product": "whatsapp", "to": "".join(ch for ch in to_phone if ch.isdigit()),
                  "type": kind, kind: media},
            timeout=30,
        )
        response.raise_for_status()
        return response.json()

    def download_media(self, media_id: str) -> tuple[bytes, str]:
        response = requests.get(
            f"https://graph.facebook.com/{self.api_version}/{media_id}",
            headers={"Authorization": f"Bearer {self.access_token}"}, timeout=30,
        )
        response.raise_for_status()
        info = response.json()
        url = str(info["url"])
        host = (urlparse(url).hostname or "").lower()
        if urlparse(url).scheme != "https" or not (
            host in {"facebook.com", "fbcdn.net", "fbsbx.com"}
            or host.endswith((".fbcdn.net", ".facebook.com", ".fbsbx.com"))
        ):
            raise ValueError("Host de mídia Meta não permitido")
        with requests.get(url, headers={"Authorization": f"Bearer {self.access_token}"},
                          timeout=60, stream=True) as file_response:
            file_response.raise_for_status()
            content = bytearray()
            for chunk in file_response.iter_content(65536):
                content.extend(chunk)
                if len(content) > 16 * 1024 * 1024:
                    raise ValueError("Mídia recebida excede 16 MB")
        return bytes(content), str(info.get("mime_type") or "")

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
