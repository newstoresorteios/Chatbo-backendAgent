"""One customer window, without rewriting provider/agent session identities."""
from datetime import datetime, timezone
import logging
from threading import Lock, Thread

from fastapi import HTTPException

from app.repositories.contact_inbox_repository import ContactInboxRepository
from app.services.conversas_service import ConversasService, PERFIL_DEPARTAMENTO, _map_conversa, _map_mensagem
from app.services.inbox_cache import CONTACT_GROUP_TTL, contact_groups_cache, conversas_cache, invalidate_conversa

logger = logging.getLogger(__name__)

_contact_sync_lock = Lock()
_syncing_contacts: set[str] = set()


def _cache_contact_groups(rows: list[dict], workspace_id: str) -> None:
    for row in rows:
        ids = [str(row["id"]), *(str(value) for value in row.get("session_ids") or [])]
        for contact_id in ids:
            contact_groups_cache.set(f"contact-group:{workspace_id}:{contact_id}", row, CONTACT_GROUP_TTL)


def _sync_contact_messages(group: dict, workspace_id: str) -> None:
    """Refresh provider messages without holding the inbox HTTP response open."""
    from app.services.ai_conversas_bridge import ai_conversas_bridge

    sync_key = f"{workspace_id}:{group['id']}"
    try:
        from app.services.inbox_cache import sync_throttle

        for session in ContactInboxRepository().sessoes(group, workspace_id):
            interval = 5 if str(session["id"]) == str(group["active_session_id"]) else 300
            if not sync_throttle.should_run(f"contact-sync:{workspace_id}:{session['id']}", interval):
                continue
            try:
                if ai_conversas_bridge.sync_messages_for_conversa(session, workspace_id):
                    invalidate_conversa(str(session["id"]), workspace_id)
            except Exception:
                logger.exception("Falha ao sincronizar sessao do historico do contato")
    finally:
        with _contact_sync_lock:
            _syncing_contacts.discard(sync_key)


def _kick_contact_sync(group: dict, workspace_id: str) -> bool:
    """Start at most one provider refresh per contact and return immediately."""
    sync_key = f"{workspace_id}:{group['id']}"
    with _contact_sync_lock:
        if sync_key in _syncing_contacts:
            return False
        _syncing_contacts.add(sync_key)
    Thread(
        target=_sync_contact_messages,
        args=(group, workspace_id),
        daemon=True,
        name=f"contact-sync-{group['id']}",
    ).start()
    return True


def map_contact(group: dict, users: dict | None = None) -> dict:
    mapped = _map_conversa(group["current_session"], users)
    return {**mapped, "id": str(group["id"]), "activeSessionId": str(group["active_session_id"]),
            "sessionIds": [str(value) for value in group["session_ids"]],
            "lastMessage": group.get("last_message") or "",
            "lastMessageAt": group["last_message_at"], "unreadCount": int(group.get("unread_count") or 0)}


class ContactInboxService:
    def __init__(self):
        self.repo = ContactInboxRepository()
        self.sessions = ConversasService()

    def obter(self, conversation_id: str, workspace_id: str) -> dict:
        if not workspace_id:
            raise HTTPException(403, "Empresa não resolvida")
        group = self.repo.obter(conversation_id, workspace_id)
        if not group:
            session = self.sessions.conversas.obter(conversation_id, workspace_id=workspace_id)
            if session and str(session["id"]) != conversation_id:
                group = self.repo.obter(str(session["id"]), workspace_id)
        if not group:
            raise HTTPException(404, "Contato não encontrado nesta empresa")
        return group

    def listar(self, workspace_id: str, *, limit: int = 60, before: str | None = None) -> list[dict]:
        if not workspace_id:
            raise HTTPException(403, "Empresa não resolvida")
        # Keep the existing background import running, but paginate the contact view.
        from app.services.conversas_service import _kick_workspace_sync
        from app.services.inbox_cache import SYNC_WORKSPACE_INTERVAL, sync_throttle
        if sync_throttle.should_run(f"ws-sync:{workspace_id}", SYNC_WORKSPACE_INTERVAL):
            _kick_workspace_sync(workspace_id)
        key = f"conversas:{workspace_id}:contacts:{limit}:{before or 'latest'}"
        cached = conversas_cache.get(key)
        if cached is not None:
            _cache_contact_groups(cached, workspace_id)
            return cached
        rows = self.repo.listar(workspace_id, limit=limit, before=before)
        _cache_contact_groups(rows, workspace_id)
        users = self.sessions._users_index()
        result = [map_contact(row, users) for row in rows]
        conversas_cache.set(key, result, 2.0)
        return result

    def mensagens(self, conversation_id: str, workspace_id: str, *, limit: int = 60,
                  before: str | None = None, before_id: str | None = None, after: str | None = None) -> list[dict]:
        if before_id:
            try:
                datetime.fromisoformat((before or "").replace("Z", "+00:00"))
            except ValueError as exc:
                raise HTTPException(422, "Informe a data da mensagem anterior junto ao identificador") from exc
        group = contact_groups_cache.get(f"contact-group:{workspace_id}:{conversation_id}")
        if group is None:
            group = self.obter(conversation_id, workspace_id)
        from app.services.inbox_cache import sync_throttle

        rows = self.repo.mensagens(
            group, workspace_id, limit=limit, before=before, before_id=before_id, after=after)

        # A abertura usa o historico persistido. A consulta ao provedor ocorre em
        # segundo plano e o polling ao vivo recebe as novas mensagens em seguida.
        if sync_throttle.should_run(f"contact-refresh:{workspace_id}:{group['id']}", 5):
            _kick_contact_sync(group, workspace_id)
        return [_map_mensagem(row) for row in rows]

    def atuar(self, conversation_id: str, workspace_id: str, action: str, *,
              actor_name: str, assignee_id: str | None = None, note: str | None = None) -> dict:
        group = self.obter(conversation_id, workspace_id)
        primary_id = str(group["active_session_id"])
        patch = {"updated_at": datetime.now(timezone.utc).isoformat()}
        if action in {"assumir", "transferir"}:
            assignee = self.sessions._usuario_ativo(assignee_id)
            patch.update(assigned_to=assignee["id"], status="active", bot_activated=False,
                         department=PERFIL_DEPARTAMENTO.get(assignee["role"], "Atendimento"))
            event = f"[Sistema] {actor_name} {'iniciou o atendimento' if action == 'assumir' else 'transferiu o atendimento para ' + assignee['name']}. O agente automático foi pausado."
        elif action == "encerrar":
            patch["status"] = "closed"
            event = f"[Sistema] Atendimento encerrado por {actor_name}." + (f" Motivo: {note.strip()}" if note else "")
        else:
            raise ValueError("Ação de contato inválida")
        updated = self.repo.atualizar_abertas(group, workspace_id, patch)
        if not updated:
            raise HTTPException(409, "O atendimento já está encerrado. Reabra para continuar.")
        self.sessions._registrar_evento(primary_id, event, workspace_id=workspace_id)
        for session in updated:
            invalidate_conversa(str(session["id"]), workspace_id)
            if action in {"assumir", "transferir"}:
                from app.services.human_takeover_bridge import mark_human_active
                mark_human_active(session, source="chatbo_contact_" + action)
        return map_contact(self.obter(conversation_id, workspace_id), self.sessions._users_index())

    def marcar_lida(self, conversation_id: str, workspace_id: str, user_id: str) -> tuple[dict, list[dict]]:
        group = self.obter(conversation_id, workspace_id)
        if str(group["current_session"].get("assigned_to") or "") != user_id:
            raise HTTPException(403, "Assuma a conversa antes de confirmar leitura")
        acks = []
        for session in self.repo.sessoes(group, workspace_id):
            if session.get("status") != "closed" and str(session.get("assigned_to") or "") == user_id:
                _, ack = self.sessions.marcar_lida(str(session["id"]), user_id, workspace_id)
                if ack:
                    acks.append(ack)
        return map_contact(self.obter(conversation_id, workspace_id), self.sessions._users_index()), acks
