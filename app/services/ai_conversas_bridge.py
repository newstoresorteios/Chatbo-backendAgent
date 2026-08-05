"""Sincroniza threads do NSAgent (ai_inbound_messages / ai_agent_responses) → conversas/mensagens.

As tabelas do NSAgentForSorteios não têm workspace_id; o escopo é por tenant único (New Store).
Threads preferem conversation_id (Brevo), com fallback em sender_key / telefone.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from app.core.workspace_scope import stamp_workspace
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)


def _thread_key(row: dict) -> str | None:
    """Alinha com NSAgent: conversation_id primeiro, depois sender_key."""
    for field in ("conversation_id", "sender_key", "sender_phone", "visitor_id"):
        value = row.get(field)
        if value is not None and str(value).strip():
            return str(value).strip()
    return None


def _channel(row: dict) -> str:
    channel = str(row.get("channel") or "whatsapp").lower()
    if channel in {"whatsapp", "instagram", "facebook", "telegram", "webchat", "sms", "email"}:
        return channel
    return "whatsapp"


def _identity_keys(conversa: dict) -> list[str]:
    keys: list[str] = []
    for field in ("external_thread_id", "contact_phone"):
        value = conversa.get(field)
        if value is not None and str(value).strip():
            text = str(value).strip()
            if text not in keys:
                keys.append(text)
    return keys


class AiConversasBridge:
    def __init__(self) -> None:
        self.conversas = ConversaRepository()
        self.mensagens = MensagemRepository()

    def _query_ai(self, table: str, column: str, value: str, *, limit: int = 500) -> list[dict]:
        try:
            resposta = (
                supabase.table(table)
                .select("*")
                .eq(column, value)
                .order("created_at", desc=False)
                .limit(limit)
                .execute()
            )
            return resposta.data or []
        except Exception as exc:
            logger.warning("Falha ao ler %s.%s=%s: %s", table, column, value, exc)
            return []

    def _list_ai_recent(self, table: str, *, page_size: int = 500) -> list[dict]:
        """Lista recente sem filtro de workspace (schema NSAgent)."""
        try:
            resposta = (
                supabase.table(table)
                .select("*")
                .order("created_at", desc=True)
                .limit(page_size)
                .execute()
            )
            return resposta.data or []
        except Exception as exc:
            logger.warning("Falha ao listar %s: %s", table, exc)
            return []

    def _fetch_inbounds_for_keys(self, keys: list[str]) -> list[dict]:
        by_id: dict[Any, dict] = {}
        for key in keys:
            for column in ("conversation_id", "sender_key", "sender_phone"):
                for row in self._query_ai("ai_inbound_messages", column, key):
                    row_id = row.get("id")
                    if row_id is not None:
                        by_id[row_id] = row
        return sorted(by_id.values(), key=lambda r: r.get("created_at") or "")

    def _fetch_responses_for_keys(self, keys: list[str], inbound_ids: list[Any]) -> list[dict]:
        by_id: dict[Any, dict] = {}
        for key in keys:
            for column in ("sender_key", "sender_phone"):
                for row in self._query_ai("ai_agent_responses", column, key):
                    row_id = row.get("id")
                    if row_id is not None:
                        by_id[row_id] = row
        for inbound_id in inbound_ids:
            if inbound_id is None:
                continue
            for row in self._query_ai("ai_agent_responses", "inbound_id", str(inbound_id)):
                row_id = row.get("id")
                if row_id is not None:
                    by_id[row_id] = row
        return sorted(by_id.values(), key=lambda r: r.get("created_at") or "")

    def _ensure_conversa(self, workspace_id: str, key: str, sample: dict) -> dict:
        conversation_id = str(sample.get("conversation_id") or "").strip() or key
        sender_key = str(
            sample.get("sender_key") or sample.get("sender_phone") or key
        ).strip()

        existing = (
            self.conversas.obter_por_contato(conversation_id, workspace_id=workspace_id)
            or self.conversas.obter_por_contato(sender_key, workspace_id=workspace_id)
            or self.conversas.obter_por_contato(key, workspace_id=workspace_id)
        )
        name = (
            sample.get("sender_name")
            or sample.get("sender_username")
            or f"Contato {key[-4:] if len(key) >= 4 else key}"
        )
        channel = _channel(sample)
        last_text = sample.get("text") or sample.get("reply_text") or ""
        last_at = sample.get("created_at") or datetime.utcnow().isoformat()

        if existing:
            # Enriquece chaves para o próximo sync de mensagens.
            patch = {}
            if conversation_id and not existing.get("external_thread_id"):
                patch["external_thread_id"] = conversation_id
            if sender_key and (
                not existing.get("contact_phone")
                or existing.get("contact_phone") == existing.get("external_thread_id")
            ):
                patch["contact_phone"] = sender_key
            if patch:
                updated = self.conversas.atualizar(
                    str(existing["id"]),
                    patch,
                    workspace_id=workspace_id,
                )
                return updated or {**existing, **patch}
            return existing

        return self.conversas.criar(
            {
                "external_thread_id": conversation_id,
                "contact_phone": sender_key,
                "customer_name": name,
                "channel": channel,
                "status": "active",
                "unread_count": 0,
                "last_message": str(last_text)[:500],
                "last_message_at": last_at,
                "protocol": f"AI-{datetime.utcnow().strftime('%Y%m%d')}-{str(key)[-4:]}",
                "bot_activated": True,
                "department": "Agente",
            },
            workspace_id=workspace_id,
        )

    def _persist_message(self, conversa_id: str, external_id: str | None, payload: dict, workspace_id: str) -> bool:
        if external_id:
            existing = self.mensagens.obter_por_external_id(external_id)
            if existing:
                if str(existing.get("conversa_id")) != str(conversa_id):
                    self.mensagens.reatribuir_conversa(str(existing["id"]), conversa_id)
                    return True
                return False

        stamped = stamp_workspace({**payload, "conversa_id": conversa_id, "external_id": external_id}, workspace_id)
        try:
            created = self.mensagens.criar(stamped)
            # Confirma persistência (RLS às vezes “aceita” sem gravar).
            if external_id and not self.mensagens.obter_por_external_id(external_id):
                if created.get("id"):
                    check = self.mensagens.listar_por_conversa(conversa_id)
                    if not any(str(m.get("id")) == str(created.get("id")) for m in check):
                        logger.warning("Mensagem %s não persistiu em mensagens", external_id)
                        return False
            return True
        except Exception as exc:
            if "workspace_id" in str(exc).lower():
                stamped.pop("workspace_id", None)
                try:
                    self.mensagens.criar(stamped)
                    return True
                except Exception as exc2:
                    logger.warning("Falha ao gravar %s: %s", external_id, exc2)
                    return False
            logger.warning("Falha ao gravar %s: %s", external_id, exc)
            return False

    def _upsert_inbound(self, conversa_id: str, row: dict, workspace_id: str) -> bool:
        inbound_id = row.get("id")
        external_id = f"ai-in-{inbound_id}" if inbound_id is not None else None
        text = str(row.get("text") or "").strip()
        if not text:
            meta = row.get("channel_metadata") or {}
            if isinstance(meta, dict) and meta.get("image_url"):
                text = "[Imagem]"
            elif isinstance(meta, dict) and meta.get("input_modality"):
                text = f"[{meta.get('input_modality')}]"
            else:
                return False
        return self._persist_message(
            conversa_id,
            external_id,
            {
                "content": text,
                "sender": "customer",
                "status": "delivered",
                "direction": "inbound",
                "provider_status": "received",
                "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
            },
            workspace_id,
        )

    def _upsert_response(self, conversa_id: str, row: dict, workspace_id: str) -> bool:
        response_id = row.get("id")
        external_id = f"ai-out-{response_id}" if response_id is not None else None
        text = str(row.get("reply_text") or "").strip()
        if not text:
            return False
        return self._persist_message(
            conversa_id,
            external_id,
            {
                "content": text,
                "sender": "ai",
                "status": "sent",
                "direction": "outbound",
                "provider_status": "sent" if row.get("provider_send_ok") else "failed",
                "created_at": row.get("created_at") or datetime.utcnow().isoformat(),
            },
            workspace_id,
        )

    def _expand_keys_from_preview(self, conversa: dict, keys: list[str]) -> list[str]:
        preview = str(conversa.get("last_message") or "").strip()
        if len(preview) < 12:
            return keys
        needle = preview[:48].replace("%", "")
        expanded = list(keys)
        for table, column in (
            ("ai_agent_responses", "reply_text"),
            ("ai_inbound_messages", "text"),
        ):
            try:
                rows = (
                    supabase.table(table)
                    .select("*")
                    .ilike(column, f"%{needle}%")
                    .order("created_at", desc=True)
                    .limit(5)
                    .execute()
                    .data
                    or []
                )
            except Exception as exc:
                logger.warning("Preview lookup %s falhou: %s", table, exc)
                continue
            for row in rows:
                for field in ("conversation_id", "sender_key", "sender_phone", "visitor_id"):
                    value = row.get(field)
                    if value is not None and str(value).strip() and str(value).strip() not in expanded:
                        expanded.append(str(value).strip())
                # responses: resolve via inbound_id
                inbound_id = row.get("inbound_id")
                if inbound_id is not None:
                    for inbound in self._query_ai("ai_inbound_messages", "id", str(inbound_id), limit=1):
                        for field in ("conversation_id", "sender_key", "sender_phone", "visitor_id"):
                            value = inbound.get(field)
                            if value is not None and str(value).strip() and str(value).strip() not in expanded:
                                expanded.append(str(value).strip())
        return expanded

    def _load_thread_rows(self, conversa: dict) -> tuple[list[dict], list[dict]]:
        keys = _identity_keys(conversa)
        keys = self._expand_keys_from_preview(conversa, keys)
        if not keys:
            return [], []

        inbounds = self._fetch_inbounds_for_keys(keys)
        extra = list(keys)
        for row in inbounds:
            for field in ("conversation_id", "sender_key", "sender_phone", "visitor_id"):
                value = row.get(field)
                if value is not None and str(value).strip() and str(value).strip() not in extra:
                    extra.append(str(value).strip())
        if len(extra) > len(keys):
            inbounds = self._fetch_inbounds_for_keys(extra)
        responses = self._fetch_responses_for_keys(extra, [row.get("id") for row in inbounds])
        return inbounds, responses

    def transcript_for_conversa(self, conversa: dict) -> list[dict]:
        """Monta histórico direto das tabelas do NSAgent (fallback de exibição)."""
        inbounds, responses = self._load_thread_rows(conversa)
        conversa_id = str(conversa.get("id") or "")
        events: list[tuple[str, dict]] = []

        for row in inbounds:
            text = str(row.get("text") or "").strip()
            if not text:
                meta = row.get("channel_metadata") or {}
                if isinstance(meta, dict) and meta.get("image_url"):
                    text = "[Imagem]"
            if not text:
                continue
            events.append(
                (
                    str(row.get("created_at") or ""),
                    {
                        "id": f"ai-in-{row.get('id')}",
                        "conversationId": conversa_id,
                        "content": text,
                        "sender": "customer",
                        "timestamp": row.get("created_at") or datetime.utcnow().isoformat(),
                        "status": "delivered",
                    },
                )
            )

        for row in responses:
            text = str(row.get("reply_text") or "").strip()
            if not text:
                continue
            events.append(
                (
                    str(row.get("created_at") or ""),
                    {
                        "id": f"ai-out-{row.get('id')}",
                        "conversationId": conversa_id,
                        "content": text,
                        "sender": "ai",
                        "timestamp": row.get("created_at") or datetime.utcnow().isoformat(),
                        "status": "sent",
                    },
                )
            )

        events.sort(key=lambda item: item[0])
        return [item[1] for item in events]

    def _sync_thread(
        self,
        workspace_id: str,
        key: str,
        inbounds: list[dict],
        responses: list[dict],
    ) -> int:
        if not inbounds and not responses:
            return 0
        sample = inbounds[-1] if inbounds else responses[-1]
        conversa = self._ensure_conversa(workspace_id, key, sample)
        conversa_id = str(conversa["id"])
        written = 0

        for row in inbounds:
            if self._upsert_inbound(conversa_id, row, workspace_id):
                written += 1
        for row in responses:
            if self._upsert_response(conversa_id, row, workspace_id):
                written += 1

        last_inbound = inbounds[-1] if inbounds else None
        last_response = responses[-1] if responses else None
        last_ts_in = str((last_inbound or {}).get("created_at") or "")
        last_ts_out = str((last_response or {}).get("created_at") or "")
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
        return written

    def sync_messages_for_conversa(self, conversa: dict, workspace_id: str | None) -> int:
        """Garante mensagens do NSAgent na conversa aberta (chamado no GET /mensagens)."""
        if not workspace_id or not conversa:
            return 0

        conversa_id = str(conversa.get("id") or "")
        if not conversa_id:
            return 0

        inbounds, responses = self._load_thread_rows(conversa)
        written = 0
        try:
            for row in inbounds:
                if self._upsert_inbound(conversa_id, row, workspace_id):
                    written += 1
            for row in responses:
                if self._upsert_response(conversa_id, row, workspace_id):
                    written += 1

            if inbounds or responses:
                sample = inbounds[-1] if inbounds else responses[-1]
                last_inbound = inbounds[-1] if inbounds else None
                last_response = responses[-1] if responses else None
                last_ts_in = str((last_inbound or {}).get("created_at") or "")
                last_ts_out = str((last_response or {}).get("created_at") or "")
                if last_ts_out > last_ts_in and last_response:
                    last_row = last_response
                    last_text = last_response.get("reply_text") or ""
                else:
                    last_row = last_inbound or last_response or sample
                    last_text = (
                        (last_inbound or {}).get("text")
                        or (last_response or {}).get("reply_text")
                        or ""
                    )
                patch = {
                    "customer_name": sample.get("sender_name")
                    or sample.get("sender_username")
                    or conversa.get("customer_name"),
                    "last_message": str(last_text)[:500],
                    "last_message_at": last_row.get("created_at") or datetime.utcnow().isoformat(),
                    "channel": _channel(sample),
                    "bot_activated": True,
                }
                conv_id = str(sample.get("conversation_id") or "").strip()
                sender_key = str(sample.get("sender_key") or sample.get("sender_phone") or "").strip()
                if conv_id:
                    patch["external_thread_id"] = conv_id
                if sender_key:
                    patch["contact_phone"] = sender_key
                self.conversas.atualizar(conversa_id, patch, workspace_id=workspace_id)
        except Exception as exc:
            logger.warning("Falha ao sincronizar mensagens da conversa %s: %s", conversa_id, exc)
            return written

        return written

    def sync_workspace(self, workspace_id: str) -> int:
        if not workspace_id:
            return 0

        inbound_rows = self._list_ai_recent("ai_inbound_messages", page_size=500)
        response_rows = self._list_ai_recent("ai_agent_responses", page_size=500)
        if not inbound_rows and not response_rows:
            return 0

        threads: dict[str, dict[str, list[dict[str, Any]]]] = {}
        for row in inbound_rows:
            key = _thread_key(row)
            if not key:
                continue
            threads.setdefault(key, {"inbounds": [], "responses": []})["inbounds"].append(row)

        for row in response_rows:
            key = _thread_key(row)
            if not key:
                continue
            threads.setdefault(key, {"inbounds": [], "responses": []})["responses"].append(row)

        synced = 0
        for key, data in threads.items():
            try:
                inbounds = sorted(data["inbounds"], key=lambda r: r.get("created_at") or "")
                responses = sorted(data["responses"], key=lambda r: r.get("created_at") or "")
                self._sync_thread(workspace_id, key, inbounds, responses)
                synced += 1
            except Exception as exc:
                logger.warning("Falha ao sincronizar thread AI %s: %s", key, exc)

        return synced


ai_conversas_bridge = AiConversasBridge()
