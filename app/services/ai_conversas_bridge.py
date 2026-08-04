"""Sincroniza threads do agente (ai_inbound_messages / ai_agent_responses) para conversas/mensagens."""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.core.workspace_scope import stamp_workspace
from app.repositories.ai.workspace_crud import WorkspaceCrudRepository
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository

logger = logging.getLogger(__name__)


def _thread_key(row: dict) -> str | None:
    for field in ("sender_key", "sender_phone", "conversation_id", "visitor_id"):
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _channel(row: dict) -> str:
    channel = str(row.get("channel") or "whatsapp").lower()
    if channel in {"whatsapp", "instagram", "facebook", "telegram", "webchat", "sms", "email"}:
        return channel
    return "whatsapp"


class AiConversasBridge:
    def __init__(self) -> None:
        self.conversas = ConversaRepository()
        self.mensagens = MensagemRepository()
        self.inbound = WorkspaceCrudRepository("ai_inbound_messages", touch_updated_at=False)
        self.responses = WorkspaceCrudRepository("ai_agent_responses", touch_updated_at=False)

    def _ensure_conversa(self, workspace_id: str, key: str, sample: dict) -> dict:
        existing = self.conversas.obter_por_contato(key, workspace_id=workspace_id)
        name = (
            sample.get("sender_name")
            or sample.get("sender_username")
            or f"Contato {key[-4:] if len(key) >= 4 else key}"
        )
        channel = _channel(sample)
        last_text = sample.get("text") or sample.get("reply_text") or ""
        last_at = sample.get("created_at") or datetime.utcnow().isoformat()

        if existing:
            return existing

        return self.conversas.criar(
            {
                "external_thread_id": key,
                "contact_phone": key,
                "customer_name": name,
                "channel": channel,
                "status": "active",
                "unread_count": 0,
                "last_message": str(last_text)[:500],
                "last_message_at": last_at,
                "protocol": f"AI-{datetime.utcnow().strftime('%Y%m%d')}-{key[-4:]}",
                "bot_activated": True,
                "department": "Agente",
            },
            workspace_id=workspace_id,
        )

    def _upsert_inbound(self, conversa_id: str, row: dict, workspace_id: str) -> None:
        inbound_id = row.get("id")
        external_id = f"ai-in-{inbound_id}" if inbound_id is not None else None
        if external_id and self.mensagens.existe_external_id(external_id):
            return
        text = str(row.get("text") or "").strip()
        if not text:
            return
        payload = stamp_workspace(
            {
                "conversa_id": conversa_id,
                "content": text,
                "sender": "customer",
                "status": "delivered",
                "direction": "inbound",
                "external_id": external_id,
                "provider_status": "received",
                "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
            },
            workspace_id,
        )
        self.mensagens.criar(payload)

    def _upsert_response(self, conversa_id: str, row: dict, workspace_id: str) -> None:
        response_id = row.get("id")
        external_id = f"ai-out-{response_id}" if response_id is not None else None
        if external_id and self.mensagens.existe_external_id(external_id):
            return
        text = str(row.get("reply_text") or "").strip()
        if not text:
            return
        payload = stamp_workspace(
            {
                "conversa_id": conversa_id,
                "content": text,
                "sender": "ai",
                "status": "sent",
                "direction": "outbound",
                "external_id": external_id,
                "provider_status": "sent" if row.get("provider_send_ok") else "failed",
                "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
            },
            workspace_id,
        )
        self.mensagens.criar(payload)

    def sync_workspace(self, workspace_id: str) -> int:
        if not workspace_id:
            return 0
        try:
            inbound_page = self.inbound.listar(workspace_id, page=1, page_size=200)
            responses_page = self.responses.listar(workspace_id, page=1, page_size=200)
            # Fallback: registros AI sem workspace_id (legado) — anexa ao workspace atual.
            if not (inbound_page.get("items") or []) and not (responses_page.get("items") or []):
                inbound_page = self.inbound.listar(None, page=1, page_size=200)
                responses_page = self.responses.listar(None, page=1, page_size=200)
        except Exception as exc:
            logger.warning("Falha ao ler tabelas AI para sync do inbox: %s", exc)
            return 0

        threads: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in inbound_page.get("items") or []:
            key = _thread_key(row)
            if not key:
                continue
            threads.setdefault(key, {"inbounds": [], "responses": []})["inbounds"].append(row)

        for row in responses_page.get("items") or []:
            key = _thread_key(row)
            if not key:
                continue
            threads.setdefault(key, {"inbounds": [], "responses": []})["responses"].append(row)

        synced = 0
        for key, data in threads.items():
            try:
                inbounds = sorted(data["inbounds"], key=lambda r: r.get("created_at") or "")
                responses = sorted(data["responses"], key=lambda r: r.get("created_at") or "")
                sample = inbounds[-1] if inbounds else responses[-1]
                conversa = self._ensure_conversa(workspace_id, key, sample)
                conversa_id = str(conversa["id"])

                for row in inbounds:
                    self._upsert_inbound(conversa_id, row, workspace_id)
                for row in responses:
                    self._upsert_response(conversa_id, row, workspace_id)

                last_inbound = inbounds[-1] if inbounds else None
                last_response = responses[-1] if responses else None
                last_ts_in = (last_inbound or {}).get("created_at") or ""
                last_ts_out = (last_response or {}).get("created_at") or ""
                if last_ts_out > last_ts_in and last_response:
                    last_row = last_response
                    last_text = last_response.get("reply_text") or ""
                else:
                    last_row = last_inbound or last_response or sample
                    last_text = (last_inbound or {}).get("text") or (last_response or {}).get("reply_text") or ""

                self.conversas.atualizar(
                    conversa_id,
                    {
                        "customer_name": sample.get("sender_name")
                        or sample.get("sender_username")
                        or conversa.get("customer_name"),
                        "last_message": str(last_text)[:500],
                        "last_message_at": last_row.get("created_at") or datetime.utcnow().isoformat(),
                        "channel": _channel(sample),
                        "status": conversa.get("status") or "active",
                        "bot_activated": True,
                    },
                    workspace_id=workspace_id,
                )
                synced += 1
            except Exception as exc:
                logger.warning("Falha ao sincronizar thread AI %s: %s", key, exc)

        return synced


ai_conversas_bridge = AiConversasBridge()
