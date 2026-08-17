"""Sincroniza threads do NSAgent (ai_inbound_messages / ai_agent_responses) → conversas/mensagens.

As tabelas do NSAgentForSorteios não têm workspace_id; o escopo é por tenant único (New Store).
Threads preferem conversation_id (Brevo), com fallback em sender_key / telefone.

A lista da Central só materializa conversas (metadados). O histórico completo
é copiado quando a conversa é aberta — evita timeout no GET /conversas.
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any, Iterable

from app.core.workspace_scope import stamp_workspace
from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

INBOUND_LIST_COLUMNS = (
    "id,created_at,conversation_id,sender_key,sender_phone,visitor_id,"
    "sender_name,sender_username,channel,text,channel_metadata"
)
RESPONSE_LIST_COLUMNS = (
    "id,created_at,sender_key,sender_phone,reply_text,channel,inbound_id"
)
INBOX_PAGE_SIZE = 500
INBOX_MAX_ROWS = 2500
IN_QUERY_CHUNK = 80


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


def _unique(values: Iterable[Any]) -> list[str]:
    seen: list[str] = []
    for value in values:
        if value is None:
            continue
        text = str(value).strip()
        if text and text not in seen:
            seen.append(text)
    return seen


class _ConversaIndex:
    """Índice em memória para não consultar conversas N vezes no sync da inbox."""

    def __init__(self, rows: list[dict]) -> None:
        self.by_identity: dict[str, dict] = {}
        for row in rows:
            self.add(row)

    def add(self, row: dict | None) -> None:
        if not row:
            return
        for field in ("external_thread_id", "contact_phone"):
            value = str(row.get(field) or "").strip()
            if value:
                self.by_identity[value] = row

    def find(self, *keys: str | None) -> dict | None:
        for key in keys:
            if not key:
                continue
            found = self.by_identity.get(str(key).strip())
            if found:
                return found
        return None


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

    def _query_ai_in(
        self,
        table: str,
        column: str,
        values: list[str],
        *,
        columns: str = "*",
        limit: int = 1000,
    ) -> list[dict]:
        keys = _unique(values)
        if not keys:
            return []
        by_id: dict[Any, dict] = {}
        for offset in range(0, len(keys), IN_QUERY_CHUNK):
            chunk = keys[offset : offset + IN_QUERY_CHUNK]
            try:
                resposta = (
                    supabase.table(table)
                    .select(columns)
                    .in_(column, chunk)
                    .order("created_at", desc=False)
                    .limit(limit)
                    .execute()
                )
                for row in resposta.data or []:
                    row_id = row.get("id")
                    if row_id is not None:
                        by_id[row_id] = row
            except Exception as exc:
                logger.warning("Falha ao ler %s.%s IN(%s): %s", table, column, len(chunk), exc)
                for value in chunk:
                    for row in self._query_ai(table, column, value, limit=min(limit, 200)):
                        row_id = row.get("id")
                        if row_id is not None:
                            by_id[row_id] = row
        return sorted(by_id.values(), key=lambda r: r.get("created_at") or "")

    def _list_ai_pages(
        self,
        table: str,
        *,
        columns: str = "*",
        page_size: int = INBOX_PAGE_SIZE,
        max_rows: int = INBOX_MAX_ROWS,
    ) -> list[dict]:
        """Lista recente sem filtro de workspace (schema NSAgent), com paginação."""
        rows: list[dict] = []
        offset = 0
        while offset < max_rows:
            try:
                end = offset + page_size - 1
                resposta = (
                    supabase.table(table)
                    .select(columns)
                    .order("created_at", desc=True)
                    .range(offset, end)
                    .execute()
                )
                batch = resposta.data or []
                rows.extend(batch)
                if len(batch) < page_size:
                    break
                offset += page_size
            except Exception as exc:
                logger.warning("Falha ao listar %s offset=%s: %s", table, offset, exc)
                break
        return rows

    def _list_ai_recent(self, table: str, *, page_size: int = 500) -> list[dict]:
        """Compat: uma página recente sem filtro de workspace."""
        return self._list_ai_pages(table, page_size=page_size, max_rows=page_size)

    def _fetch_inbounds_for_keys(self, keys: list[str]) -> list[dict]:
        by_id: dict[Any, dict] = {}
        for column in ("conversation_id", "sender_key", "sender_phone", "visitor_id"):
            for row in self._query_ai_in("ai_inbound_messages", column, keys, limit=1000):
                row_id = row.get("id")
                if row_id is not None:
                    by_id[row_id] = row
        return sorted(by_id.values(), key=lambda r: r.get("created_at") or "")

    def _fetch_responses_for_keys(self, keys: list[str], inbound_ids: list[Any]) -> list[dict]:
        by_id: dict[Any, dict] = {}
        inbound_keys = [str(item) for item in inbound_ids if item is not None]
        if inbound_keys:
            for row in self._query_ai_in(
                "ai_agent_responses",
                "inbound_id",
                inbound_keys,
                limit=1000,
            ):
                row_id = row.get("id")
                if row_id is not None:
                    by_id[row_id] = row
        for column in ("sender_key", "sender_phone"):
            for row in self._query_ai_in("ai_agent_responses", column, keys, limit=500):
                row_id = row.get("id")
                if row_id is not None:
                    by_id[row_id] = row
        return sorted(by_id.values(), key=lambda r: r.get("created_at") or "")

    def _ensure_conversa(
        self,
        workspace_id: str,
        key: str,
        sample: dict,
        index: _ConversaIndex | None = None,
    ) -> dict:
        conversation_id = str(sample.get("conversation_id") or "").strip() or key
        sender_key = str(
            sample.get("sender_key") or sample.get("sender_phone") or key
        ).strip()

        existing = index.find(conversation_id, sender_key, key) if index else None
        if existing is None:
            existing = (
                self.conversas.obter_por_contato(conversation_id, workspace_id=workspace_id)
                or self.conversas.obter_por_contato(sender_key, workspace_id=workspace_id)
                or self.conversas.obter_por_contato(key, workspace_id=workspace_id)
            )
            if index:
                index.add(existing)

        name = (
            sample.get("sender_name")
            or sample.get("sender_username")
            or f"Contato {key[-4:] if len(key) >= 4 else key}"
        )
        channel = _channel(sample)
        last_text = sample.get("text") or sample.get("reply_text") or ""
        last_at = sample.get("created_at") or datetime.utcnow().isoformat()

        if existing:
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
                merged = updated or {**existing, **patch}
                if index:
                    index.add(merged)
                return merged
            return existing

        created = self.conversas.criar(
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
        if index:
            index.add(created)
        return created

    def _persist_message(
        self,
        conversa_id: str,
        external_id: str | None,
        payload: dict,
        workspace_id: str,
        *,
        known_new: bool = False,
    ) -> bool:
        if external_id and not known_new:
            existing = self.mensagens.obter_por_external_id(external_id)
            if existing:
                if str(existing.get("conversa_id")) != str(conversa_id):
                    self.mensagens.reatribuir_conversa(str(existing["id"]), conversa_id)
                    return True
                return False

        stamped = stamp_workspace({**payload, "conversa_id": conversa_id, "external_id": external_id}, workspace_id)
        try:
            self.mensagens.criar(stamped)
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

    def _upsert_inbound(
        self,
        conversa_id: str,
        row: dict,
        workspace_id: str,
        *,
        known_new: bool = False,
    ) -> bool:
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
            known_new=known_new,
        )

    def _upsert_response(
        self,
        conversa_id: str,
        row: dict,
        workspace_id: str,
        *,
        known_new: bool = False,
    ) -> bool:
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
            known_new=known_new,
        )

    def _load_thread_rows(self, conversa: dict) -> tuple[list[dict], list[dict]]:
        keys = _identity_keys(conversa)
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

    def _last_preview(self, inbounds: list[dict], responses: list[dict], sample: dict) -> tuple[str, str]:
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
        last_at = last_row.get("created_at") if last_row else datetime.utcnow().isoformat()
        return str(last_text)[:500], last_at or datetime.utcnow().isoformat()

    def _group_threads(
        self,
        inbound_rows: list[dict],
        response_rows: list[dict],
    ) -> dict[str, dict[str, list[dict[str, Any]]]]:
        threads: dict[str, dict[str, list[dict[str, Any]]]] = {}
        inbound_alias: dict[str, str] = {}

        for row in inbound_rows:
            key = _thread_key(row)
            if not key:
                continue
            threads.setdefault(key, {"inbounds": [], "responses": []})["inbounds"].append(row)
            for field in ("sender_key", "sender_phone", "visitor_id"):
                alias = str(row.get(field) or "").strip()
                if alias:
                    inbound_alias[alias] = key

        for row in response_rows:
            inbound_id = row.get("inbound_id")
            key = None
            if inbound_id is not None:
                for inbound in inbound_rows:
                    if inbound.get("id") == inbound_id:
                        key = _thread_key(inbound)
                        break
            if not key:
                sender = str(row.get("sender_key") or row.get("sender_phone") or "").strip()
                key = inbound_alias.get(sender) or _thread_key(row)
            if not key:
                continue
            threads.setdefault(key, {"inbounds": [], "responses": []})["responses"].append(row)

        return threads

    def _sync_thread_inbox(
        self,
        workspace_id: str,
        key: str,
        inbounds: list[dict],
        responses: list[dict],
        index: _ConversaIndex,
    ) -> bool:
        """Cria/atualiza a conversa na Central sem copiar o histórico de mensagens."""
        if not inbounds and not responses:
            return False
        sample = inbounds[-1] if inbounds else responses[-1]
        conversa = self._ensure_conversa(workspace_id, key, sample, index)
        conversa_id = str(conversa["id"])
        last_text, last_at = self._last_preview(inbounds, responses, sample)
        patch = {
            "customer_name": sample.get("sender_name")
            or sample.get("sender_username")
            or conversa.get("customer_name"),
            "last_message": last_text,
            "last_message_at": last_at,
            "channel": _channel(sample),
            "status": conversa.get("status") or "active",
        }
        conv_id = str(sample.get("conversation_id") or "").strip()
        sender_key = str(sample.get("sender_key") or sample.get("sender_phone") or "").strip()
        if conv_id:
            patch["external_thread_id"] = conv_id
        if sender_key:
            patch["contact_phone"] = sender_key
        if not conversa.get("assigned_to") and conversa.get("bot_activated") is not False:
            patch["bot_activated"] = True
        updated = self.conversas.atualizar(conversa_id, patch, workspace_id=workspace_id)
        index.add(updated or {**conversa, **patch})
        return True

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
            existing_ext = self.mensagens.listar_external_ids(conversa_id)
            for row in inbounds:
                inbound_id = row.get("id")
                external_id = f"ai-in-{inbound_id}" if inbound_id is not None else None
                if external_id and external_id in existing_ext:
                    continue
                if self._upsert_inbound(conversa_id, row, workspace_id, known_new=bool(external_id)):
                    written += 1
                    if external_id:
                        existing_ext.add(external_id)
            for row in responses:
                response_id = row.get("id")
                external_id = f"ai-out-{response_id}" if response_id is not None else None
                if external_id and external_id in existing_ext:
                    continue
                if self._upsert_response(conversa_id, row, workspace_id, known_new=bool(external_id)):
                    written += 1
                    if external_id:
                        existing_ext.add(external_id)

            if inbounds or responses:
                sample = inbounds[-1] if inbounds else responses[-1]
                last_text, last_at = self._last_preview(inbounds, responses, sample)
                patch = {
                    "customer_name": sample.get("sender_name")
                    or sample.get("sender_username")
                    or conversa.get("customer_name"),
                    "last_message": last_text,
                    "last_message_at": last_at,
                    "channel": _channel(sample),
                }
                if not conversa.get("assigned_to") and conversa.get("bot_activated") is not False:
                    patch["bot_activated"] = True
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
        """Materializa todas as threads recentes do NSAgent na inbox (sem copiar mensagens)."""
        if not workspace_id:
            return 0

        inbound_rows = self._list_ai_pages("ai_inbound_messages", columns=INBOUND_LIST_COLUMNS)
        response_rows = self._list_ai_pages("ai_agent_responses", columns=RESPONSE_LIST_COLUMNS)
        if not inbound_rows and not response_rows:
            return 0

        threads = self._group_threads(inbound_rows, response_rows)
        existing_rows = self.conversas.listar(workspace_id=workspace_id)
        try:
            existing_rows = existing_rows + self.conversas.listar_legado_sem_workspace()
        except Exception as exc:
            logger.warning("Falha ao listar conversas legadas no sync: %s", exc)
        index = _ConversaIndex(existing_rows)

        synced = 0
        for key, data in threads.items():
            try:
                inbounds = sorted(data["inbounds"], key=lambda r: r.get("created_at") or "")
                responses = sorted(data["responses"], key=lambda r: r.get("created_at") or "")
                if self._sync_thread_inbox(workspace_id, key, inbounds, responses, index):
                    synced += 1
            except Exception as exc:
                logger.warning("Falha ao sincronizar thread AI %s: %s", key, exc)

        return synced


ai_conversas_bridge = AiConversasBridge()
