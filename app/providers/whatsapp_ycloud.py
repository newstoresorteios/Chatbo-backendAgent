"""Small YCloud REST adapter for one server-configured WhatsApp number."""

from __future__ import annotations

import hashlib
import hmac
import re
import time
from urllib.parse import quote

import requests


_E164 = re.compile(r"^\+[1-9]\d{7,14}$")
_BASE = "https://api.ycloud.com/v2/whatsapp"


def normalize_phone(value: str) -> str:
    phone = "+" + "".join(character for character in str(value or "") if character.isdigit())
    if not _E164.fullmatch(phone):
        raise ValueError("Número de telefone inválido; use E.164")
    return phone


def verify_signature(body: bytes, header: str | None, secret: str | None, *, now: int | None = None) -> bool:
    """Verify YCloud's `t=<unix>,s=<hex>` HMAC over timestamp + '.' + raw body."""
    if not header or not secret:
        return False
    values = {}
    for part in header.split(","):
        key, separator, value = part.strip().partition("=")
        if separator and key in {"t", "s"}:
            values[key] = value.strip()
    stamp, signature = values.get("t", ""), values.get("s", "")
    if not stamp.isascii() or not stamp.isdigit() or not re.fullmatch(r"[0-9a-fA-F]{64}", signature):
        return False
    current = int(time.time()) if now is None else now
    if abs(current - int(stamp)) > 300:
        return False
    expected = hmac.new(secret.encode("utf-8"), stamp.encode("ascii") + b"." + body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature.lower())


class YCloudProvider:
    def __init__(self, api_key: str, phone_number: str, waba_id: str, phone_number_id: str | None = None):
        self.api_key = str(api_key or "").strip()
        self.phone_number = normalize_phone(phone_number)
        self.waba_id = str(waba_id or "").strip()
        self.phone_number_id = str(phone_number_id or "").strip() or None
        if not self.api_key or not self.waba_id:
            raise ValueError("Credenciais YCloud incompletas")

    def _headers(self) -> dict[str, str]:
        return {"X-API-Key": self.api_key, "Accept": "application/json"}

    def validate_number(self) -> dict:
        response = requests.get(
            f"{_BASE}/phoneNumbers/{quote(self.waba_id, safe='')}/{quote(self.phone_number, safe='')}",
            headers=self._headers(), timeout=15,
        )
        response.raise_for_status()
        data = response.json()
        if not isinstance(data, dict):
            raise ValueError("Resposta inesperada da YCloud")
        if str(data.get("wabaId") or "") != self.waba_id:
            raise ValueError("WABA ID da YCloud não corresponde ao configurado")
        if str(data.get("phoneNumber") or "") != self.phone_number:
            raise ValueError("Número da YCloud não corresponde ao configurado")
        if self.phone_number_id and str(data.get("id") or "") != self.phone_number_id:
            raise ValueError("Phone Number ID da YCloud não corresponde ao configurado")
        if data.get("status") != "CONNECTED":
            raise ValueError("Número YCloud ainda não está conectado")
        return data

    def send_text(self, to_phone: str, body: str) -> str:
        recipient = normalize_phone(to_phone)
        text = str(body or "").strip()
        if not text or len(text) > 4096:
            raise ValueError("Texto WhatsApp deve ter entre 1 e 4096 caracteres")
        response = requests.post(
            f"{_BASE}/messages", headers=self._headers(),
            json={"from": self.phone_number, "to": recipient, "type": "text", "text": {"body": text}},
            timeout=20,
        )
        response.raise_for_status()
        data = response.json()
        message_id = str(data.get("id") or "") if isinstance(data, dict) else ""
        if not message_id:
            raise ValueError("YCloud não retornou ID da mensagem")
        return message_id
