from datetime import datetime, timedelta
import logging
import threading

from fastapi import HTTPException

from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.repositories.usuario_repository import UsuarioRepository

logger = logging.getLogger(__name__)

PERFIL_DEPARTAMENTO = {
    "admin": "Comercial",
    "supervisor": "Suporte",
    "vendedor": "Vendas",
    "user": "Atendimento",
}


def _map_conversa(row: dict, users: dict[str, dict] | None = None) -> dict:
    assigned_id = row.get("assigned_to")
    assigned_user = (users or {}).get(str(assigned_id)) if assigned_id else None
    return {
        "id": str(row.get("id")),
        "customerId": str(row.get("cliente_mercos_id") or ""),
        "customerName": row.get("customer_name") or "Cliente",
        "customerAvatar": row.get("customer_avatar"),
        "lastMessage": row.get("last_message") or "",
        "lastMessageAt": row.get("last_message_at") or row.get("created_at") or datetime.utcnow().isoformat(),
        "status": row.get("status") or "active",
        "unreadCount": int(row.get("unread_count") or 0),
        "channel": row.get("channel") or "whatsapp",
        "department": row.get("department"),
        "protocol": row.get("protocol"),
        "assignedTo": str(assigned_id) if assigned_id else None,
        "assignedName": assigned_user.get("name") if assigned_user else None,
        "canalId": row.get("canal_id"),
        "contactPhone": row.get("contact_phone"),
    }


def _map_mensagem(row: dict) -> dict:
    external_id = row.get("external_id")
    return {
        "id": str(row.get("id")),
        "conversationId": str(row.get("conversa_id")),
        "content": row.get("content") or "",
        "sender": row.get("sender") or "agent",
        "timestamp": row.get("created_at") or datetime.utcnow().isoformat(),
        "status": row.get("status") or "sent",
        "externalId": str(external_id) if external_id else None,
    }


def _message_dedupe_keys(msg: dict) -> list[str]:
    """Chaves estáveis para unir mensagens persistidas + transcript NSAgent."""
    keys: list[str] = []
    external = msg.get("externalId") or msg.get("external_id")
    msg_id = msg.get("id")
    if external:
        keys.append(f"ext:{external}")
    # Transcript usa id=ai-in-123; sync grava external_id=ai-in-123 e id=uuid.
    if msg_id and str(msg_id).startswith("ai-"):
        keys.append(f"ext:{msg_id}")
    if msg_id:
        keys.append(f"id:{msg_id}")
    content = " ".join(str(msg.get("content") or "").split()).strip().lower()
    sender = str(msg.get("sender") or "")
    ts = str(msg.get("timestamp") or "")[:16]  # até minutos
    if content and sender:
        keys.append(f"fp:{sender}:{ts}:{content[:180]}")
    return keys


def _merge_mensagens(mapped: list[dict], transcript: list[dict]) -> list[dict]:
    """Une mensagens locais com transcript NSAgent sem duplicar."""
    items: list[dict] = []
    index: dict[str, int] = {}

    def upsert(msg: dict, prefer: bool = False) -> None:
        keys = _message_dedupe_keys(msg)
        if not keys:
            return
        existing_idx = next((index[k] for k in keys if k in index), None)
        if existing_idx is not None:
            if prefer:
                items[existing_idx] = msg
            for k in keys:
                index[k] = existing_idx
            return
        idx = len(items)
        items.append(msg)
        for k in keys:
            index[k] = idx

    for msg in mapped:
        upsert(msg, prefer=False)
    for msg in transcript:
        upsert(msg, prefer=True)

    return sorted(items, key=lambda m: m.get("timestamp") or "")


def _format_atendente_outbound(actor_name: str | None, content: str) -> str:
    """Formato WhatsApp: 'Felipe:\\nBoa Noite!'."""
    body = (content or "").strip()
    name = (actor_name or "").strip()
    if not body:
        return body
    if not name:
        return body
    prefix = f"{name}:"
    if body.lower().startswith(prefix.lower()):
        rest = body[len(prefix) :].lstrip(" \n")
        return f"{prefix}\n{rest}" if rest else prefix
    return f"{prefix}\n{body}"


_SYNC_LOCK = threading.Lock()
_SYNC_RUNNING: set[str] = set()


def _kick_workspace_sync(workspace_id: str) -> None:
    """Sync NSAgent em background para o GET /conversas não estourar timeout."""
    if not workspace_id:
        return
    with _SYNC_LOCK:
        if workspace_id in _SYNC_RUNNING:
            return
        _SYNC_RUNNING.add(workspace_id)

    def _run() -> None:
        try:
            from app.services.ai_conversas_bridge import ai_conversas_bridge
            from app.services.inbox_cache import conversas_cache

            synced = ai_conversas_bridge.sync_workspace(workspace_id)
            if synced:
                logger.info(
                    "Inbox sync AI (bg): %s thread(s) para workspace %s",
                    synced,
                    workspace_id,
                )
                conversas_cache.delete(f"conversas:{workspace_id}")
                conversas_cache.delete("conversas:all")
        except Exception as exc:
            logger.warning("Sync AI background falhou: %s", exc)
        finally:
            with _SYNC_LOCK:
                _SYNC_RUNNING.discard(workspace_id)

    threading.Thread(
        target=_run,
        daemon=True,
        name=f"ai-inbox-sync-{workspace_id[:8]}",
    ).start()


class ConversasService:

    def __init__(self):
        self.conversas = ConversaRepository()
        self.mensagens = MensagemRepository()
        self.usuarios = UsuarioRepository()

    def _users_index(self) -> dict[str, dict]:
        try:
            from app.services.inbox_cache import conversas_cache

            cached = conversas_cache.get("users-index")
            if cached is not None:
                return cached
        except Exception:
            cached = None

        index: dict[str, dict] = {}
        for row in self.usuarios.listar():
            uid = str(row.get("id"))
            index[uid] = {
                "id": uid,
                "name": row.get("nome") or row.get("email", "").split("@")[0],
                "role": row.get("perfil") or "user",
                "active": row.get("ativo") is not False,
            }
        try:
            from app.services.inbox_cache import conversas_cache

            conversas_cache.set("users-index", index, 30.0)
        except Exception:
            pass
        return index

    def _usuario_ativo(self, usuario_id: str) -> dict:
        usuario = self.usuarios.buscar_por_id(usuario_id)
        if not usuario or usuario.get("ativo") is False:
            raise HTTPException(status_code=404, detail="Atendente não encontrado ou inativo")
        return {
            "id": str(usuario.get("id")),
            "name": usuario.get("nome") or usuario.get("email", "").split("@")[0],
            "role": usuario.get("perfil") or "user",
        }

    def _obter_conversa(self, conversa_id: str, workspace_id: str | None = None) -> dict:
        conversa = self.conversas.obter(conversa_id, workspace_id=workspace_id)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        return conversa

    def _registrar_evento(
        self,
        conversa_id: str,
        content: str,
        workspace_id: str | None = None,
    ) -> None:
        self.mensagens.criar({
            "conversa_id": conversa_id,
            "content": content.strip(),
            "sender": "agent",
            "status": "sent",
        })
        self.conversas.atualizar(
            conversa_id,
            {
                "last_message": content.strip(),
                "last_message_at": datetime.utcnow().isoformat(),
            },
            workspace_id=workspace_id,
        )

    def _listar_rows_inbox(self, workspace_id: str | None) -> list[dict]:
        rows = self.conversas.listar(workspace_id=workspace_id)
        if not workspace_id:
            return rows
        # Une legado (sem workspace_id) para não esconder threads WhatsApp/NSAgent antigas.
        try:
            legado = self.conversas.listar_legado_sem_workspace()
        except Exception as exc:
            logger.warning("Falha ao listar conversas legadas: %s", exc)
            return rows
        seen = {str(row.get("id")) for row in rows}
        merged = list(rows)
        for row in legado:
            row_id = str(row.get("id") or "")
            if row_id and row_id not in seen:
                merged.append(row)
                seen.add(row_id)
        merged.sort(key=lambda r: r.get("last_message_at") or r.get("created_at") or "", reverse=True)
        return merged

    def listar_conversas(self, workspace_id: str | None = None) -> list[dict]:
        cache_key = f"conversas:{workspace_id or 'all'}"
        cached = None
        try:
            from app.services.inbox_cache import conversas_cache

            cached = conversas_cache.get(cache_key)
        except Exception:
            cached = None

        if workspace_id:
            try:
                from app.services.inbox_cache import SYNC_WORKSPACE_INTERVAL, sync_throttle

                if sync_throttle.should_run(f"ws-sync:{workspace_id}", SYNC_WORKSPACE_INTERVAL):
                    _kick_workspace_sync(workspace_id)
            except Exception as exc:
                logger.warning("Sync AI → conversas falhou: %s", exc)

        if cached is not None:
            return cached

        try:
            rows = self._listar_rows_inbox(workspace_id)
        except Exception as exc:
            if "conversas" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail="Tabela conversas não existe. Execute supabase/001_conversas_mensagens.sql no Supabase.",
                ) from exc
            raise
        users = self._users_index()
        mapped = [_map_conversa(row, users) for row in rows]
        try:
            from app.services.inbox_cache import CONVERSAS_TTL, conversas_cache

            conversas_cache.set(cache_key, mapped, CONVERSAS_TTL)
        except Exception:
            pass
        return mapped

    def listar_mensagens(self, conversa_id: str, workspace_id: str | None = None) -> list[dict]:
        cache_key = f"mensagens:{conversa_id}"
        try:
            from app.services.inbox_cache import MENSAGENS_TTL, mensagens_cache

            cached = mensagens_cache.get(cache_key)
            if cached is not None:
                return cached
        except Exception:
            pass

        conversa = self.conversas.obter(conversa_id, workspace_id=workspace_id)
        if not conversa and workspace_id:
            # Conversas legadas / sync sem workspace no filtro.
            conversa = self.conversas.obter(conversa_id, workspace_id=None)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")

        # Sync NSAgent com throttle — evita N queries a cada poll de 2s.
        written = 0
        try:
            from app.services.ai_conversas_bridge import ai_conversas_bridge
            from app.services.inbox_cache import SYNC_MSG_INTERVAL, sync_throttle

            ws = workspace_id or conversa.get("workspace_id")
            if sync_throttle.should_run(f"msg-sync:{conversa_id}", SYNC_MSG_INTERVAL):
                written = ai_conversas_bridge.sync_messages_for_conversa(conversa, ws)
                if written:
                    logger.info(
                        "Inbox sync mensagens: %s nova(s) na conversa %s",
                        written,
                        conversa_id,
                    )
        except Exception as exc:
            logger.warning("Sync mensagens AI falhou para %s: %s", conversa_id, exc)

        rows = self.mensagens.listar_por_conversa(conversa_id)
        mapped = [_map_mensagem(row) for row in rows]

        # Transcript só como fallback se a tabela mensagens ainda estiver vazia.
        if not mapped:
            try:
                from app.services.ai_conversas_bridge import ai_conversas_bridge

                transcript = ai_conversas_bridge.transcript_for_conversa(conversa)
                if transcript:
                    mapped = _merge_mensagens([], transcript)
            except Exception as exc:
                logger.warning("Transcript AI falhou para %s: %s", conversa_id, exc)

        if written:
            try:
                from app.services.inbox_cache import invalidate_conversa

                invalidate_conversa(conversa_id, workspace_id or conversa.get("workspace_id"))
            except Exception:
                pass

        try:
            from app.services.inbox_cache import MENSAGENS_TTL, mensagens_cache

            mensagens_cache.set(cache_key, mapped, MENSAGENS_TTL)
        except Exception:
            pass
        return mapped

    def enviar_mensagem(
        self,
        conversa_id: str,
        content: str,
        sender: str = "agent",
        workspace_id: str | None = None,
        actor_user_id: str | None = None,
        actor_name: str | None = None,
    ) -> dict:
        if sender not in {"customer", "agent", "ai"}:
            sender = "agent"

        conversa = self.conversas.obter(conversa_id, workspace_id=workspace_id)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        if conversa.get("status") == "closed":
            raise HTTPException(status_code=400, detail="Conversa encerrada — reabra para enviar mensagens")

        if sender == "agent":
            assigned = str(conversa.get("assigned_to") or "")
            if not actor_user_id or assigned != str(actor_user_id):
                raise HTTPException(
                    status_code=403,
                    detail="Assuma a conversa antes de enviar mensagens ao cliente",
                )

        outbound_text = content.strip()
        if sender == "agent":
            name = (actor_name or "").strip()
            if not name and actor_user_id:
                user = self._users_index().get(str(actor_user_id))
                name = (user or {}).get("name") or ""
            outbound_text = _format_atendente_outbound(name, outbound_text)

        mensagem = self.mensagens.criar({
            "conversa_id": conversa_id,
            "content": outbound_text,
            "sender": sender,
            "status": "sent",
            "direction": "outbound",
        })

        conv_patch = {
            "last_message": outbound_text,
            "last_message_at": datetime.utcnow().isoformat(),
            "unread_count": 0,
        }
        if sender == "agent":
            # Garante que o NSAgent continue pausado enquanto o humano atende.
            conv_patch["bot_activated"] = False
        self.conversas.atualizar(
            conversa_id,
            conv_patch,
            workspace_id=workspace_id,
        )

        delivery: dict = {"sent": False, "reason": "Brevo não tentado"}
        if sender in {"agent", "ai"}:
            from app.services.brevo_outbound_service import brevo_outbound_service

            # New Store: somente Brevo (mesmo caminho do NSAgentForSorteios).
            if not brevo_outbound_service.configurado():
                delivery = {
                    "sent": False,
                    "reason": (
                        "BREVO_API_KEY ausente no Render. Copie as variáveis Brevo do "
                        "NSAgentForSorteios (BREVO_API_KEY, BREVO_SENDER_NUMBER, "
                        "BREVO_AGENT_ID ou BREVO_AGENT_EMAIL/NAME, BREVO_REPLY_MODE)."
                    ),
                    "brevoStatus": brevo_outbound_service.status(),
                }
            else:
                delivery = brevo_outbound_service.enviar_para_conversa(conversa, outbound_text)
                delivery["brevoStatus"] = brevo_outbound_service.status()

            if mensagem.get("id"):
                self.mensagens.atualizar(
                    str(mensagem["id"]),
                    {
                        "status": "sent" if delivery.get("sent") else "failed",
                        "provider_status": "sent" if delivery.get("sent") else "failed",
                    },
                )

            if not delivery.get("sent"):
                logger.error(
                    "Falha envio Brevo conversa=%s reason=%s",
                    conversa_id,
                    delivery.get("reason"),
                )
                raise HTTPException(
                    status_code=502,
                    detail=delivery.get("reason")
                    or "Não foi possível entregar a mensagem ao cliente via Brevo",
                )
        elif sender == "customer":
            try:
                from app.services.chatbot_service import chatbot_service

                channel = conversa.get("channel") or "whatsapp"
                chatbot_service.handle_inbound(conversa_id, content.strip(), channel)
            except Exception as exc:
                logger.warning("Chatbot runtime falhou: %s", exc)

        mapped = _map_mensagem(mensagem)
        mapped["delivery"] = delivery
        try:
            from app.services.inbox_cache import invalidate_conversa

            invalidate_conversa(conversa_id, workspace_id or conversa.get("workspace_id"))
        except Exception:
            pass
        return mapped

    def transferir(
        self,
        conversa_id: str,
        assignee_id: str,
        actor_name: str,
        workspace_id: str | None = None,
        *,
        assumindo: bool = False,
    ) -> dict:
        self._obter_conversa(conversa_id, workspace_id=workspace_id)
        assignee = self._usuario_ativo(assignee_id)
        department = PERFIL_DEPARTAMENTO.get(assignee["role"], "Atendimento")

        row = self.conversas.atualizar(
            conversa_id,
            {
                "assigned_to": assignee["id"],
                "department": department,
                "status": "active",
                # Pausa o NSAgent / robô local enquanto houver atendente humano.
                "bot_activated": False,
            },
            workspace_id=workspace_id,
        )
        if assumindo:
            event = (
                f"[Sistema] {assignee['name']} iniciou o atendimento "
                f"({department}). O agente automático foi pausado."
            )
        else:
            event = (
                f"[Sistema] Atendimento transferido para {assignee['name']} "
                f"({department}) por {actor_name}. O agente automático permanece pausado."
            )
        self._registrar_evento(
            conversa_id,
            event,
            workspace_id=workspace_id,
        )
        try:
            from app.services.inbox_cache import invalidate_conversa

            invalidate_conversa(conversa_id, workspace_id)
        except Exception:
            pass
        users = self._users_index()
        return _map_conversa(
            row or self._obter_conversa(conversa_id, workspace_id=workspace_id),
            users,
        )

    def assumir(
        self,
        conversa_id: str,
        user_id: str,
        actor_name: str,
        workspace_id: str | None = None,
    ) -> dict:
        return self.transferir(
            conversa_id,
            user_id,
            actor_name,
            workspace_id=workspace_id,
            assumindo=True,
        )

    def encerrar(
        self,
        conversa_id: str,
        actor_name: str,
        note: str | None = None,
        workspace_id: str | None = None,
    ) -> dict:
        self._obter_conversa(conversa_id, workspace_id=workspace_id)
        row = self.conversas.atualizar(
            conversa_id,
            {"status": "closed"},
            workspace_id=workspace_id,
        )
        detail = f" Motivo: {note.strip()}" if note and note.strip() else ""
        self._registrar_evento(
            conversa_id,
            f"[Sistema] Atendimento encerrado por {actor_name}.{detail}",
            workspace_id=workspace_id,
        )
        try:
            from app.services.inbox_cache import invalidate_conversa

            invalidate_conversa(conversa_id, workspace_id)
        except Exception:
            pass
        users = self._users_index()
        return _map_conversa(
            row or self._obter_conversa(conversa_id, workspace_id=workspace_id),
            users,
        )

    def reativar(
        self,
        conversa_id: str,
        actor_name: str,
        workspace_id: str | None = None,
    ) -> dict:
        self._obter_conversa(conversa_id, workspace_id=workspace_id)
        row = self.conversas.atualizar(
            conversa_id,
            {"status": "active"},
            workspace_id=workspace_id,
        )
        self._registrar_evento(
            conversa_id,
            f"[Sistema] Atendimento reaberto por {actor_name}.",
            workspace_id=workspace_id,
        )
        try:
            from app.services.inbox_cache import invalidate_conversa

            invalidate_conversa(conversa_id, workspace_id)
        except Exception:
            pass
        users = self._users_index()
        return _map_conversa(
            row or self._obter_conversa(conversa_id, workspace_id=workspace_id),
            users,
        )

    def reservar_produto(
        self,
        conversa_id: str,
        product_id: str,
        product_name: str,
        actor_name: str,
        quantity: int = 1,
        workspace_id: str | None = None,
    ) -> dict:
        conversa = self._obter_conversa(conversa_id, workspace_id=workspace_id)
        if conversa.get("status") == "closed":
            raise HTTPException(status_code=400, detail="Não é possível reservar em conversa encerrada")

        qty = max(1, quantity)
        expires_at = (datetime.utcnow() + timedelta(hours=48)).strftime("%d/%m/%Y %H:%M UTC")
        label = product_name.strip() or product_id
        self._registrar_evento(
            conversa_id,
            (
                f"[Sistema] Reserva de {qty}x {label} (ref. {product_id}) "
                f"registrada por {actor_name}. Validade: 48h (até {expires_at})."
            ),
            workspace_id=workspace_id,
        )
        users = self._users_index()
        return _map_conversa(
            self._obter_conversa(conversa_id, workspace_id=workspace_id),
            users,
        )

    def contar_conversas(self, workspace_id: str | None = None) -> int:
        try:
            return self.conversas.contar(workspace_id=workspace_id)
        except Exception:
            return 0
