from datetime import datetime, timedelta
import logging

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
    return {
        "id": str(row.get("id")),
        "conversationId": str(row.get("conversa_id")),
        "content": row.get("content") or "",
        "sender": row.get("sender") or "agent",
        "timestamp": row.get("created_at") or datetime.utcnow().isoformat(),
        "status": row.get("status") or "sent",
    }


class ConversasService:

    def __init__(self):
        self.conversas = ConversaRepository()
        self.mensagens = MensagemRepository()
        self.usuarios = UsuarioRepository()

    def _users_index(self) -> dict[str, dict]:
        index: dict[str, dict] = {}
        for row in self.usuarios.listar():
            uid = str(row.get("id"))
            index[uid] = {
                "id": uid,
                "name": row.get("nome") or row.get("email", "").split("@")[0],
                "role": row.get("perfil") or "user",
                "active": row.get("ativo") is not False,
            }
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

    def _obter_conversa(self, conversa_id: str) -> dict:
        conversa = self.conversas.obter(conversa_id)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        return conversa

    def _registrar_evento(self, conversa_id: str, content: str) -> None:
        self.mensagens.criar({
            "conversa_id": conversa_id,
            "content": content.strip(),
            "sender": "agent",
            "status": "sent",
        })
        self.conversas.atualizar(conversa_id, {
            "last_message": content.strip(),
            "last_message_at": datetime.utcnow().isoformat(),
        })

    def listar_conversas(self) -> list[dict]:
        try:
            rows = self.conversas.listar()
        except Exception as exc:
            if "conversas" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail="Tabela conversas não existe. Execute supabase/001_conversas_mensagens.sql no Supabase.",
                ) from exc
            raise
        users = self._users_index()
        return [_map_conversa(row, users) for row in rows]

    def listar_mensagens(self, conversa_id: str) -> list[dict]:
        if not self.conversas.obter(conversa_id):
            raise HTTPException(status_code=404, detail="Conversa não encontrada")

        rows = self.mensagens.listar_por_conversa(conversa_id)
        return [_map_mensagem(row) for row in rows]

    def enviar_mensagem(self, conversa_id: str, content: str, sender: str = "agent") -> dict:
        if sender not in {"customer", "agent", "ai"}:
            sender = "agent"

        conversa = self.conversas.obter(conversa_id)
        if not conversa:
            raise HTTPException(status_code=404, detail="Conversa não encontrada")
        if conversa.get("status") == "closed":
            raise HTTPException(status_code=400, detail="Conversa encerrada — reabra para enviar mensagens")

        mensagem = self.mensagens.criar({
            "conversa_id": conversa_id,
            "content": content.strip(),
            "sender": sender,
            "status": "sent",
            "direction": "outbound",
        })

        self.conversas.atualizar(conversa_id, {
            "last_message": content.strip(),
            "last_message_at": datetime.utcnow().isoformat(),
            "unread_count": 0,
        })

        if sender in {"agent", "ai"}:
            from app.services.whatsapp_service import whatsapp_service

            whatsapp_service.enviar_para_conversa(
                conversa,
                content.strip(),
                str(mensagem.get("id")),
            )
        elif sender == "customer":
            try:
                from app.services.chatbot_service import chatbot_service

                channel = conversa.get("channel") or "whatsapp"
                chatbot_service.handle_inbound(conversa_id, content.strip(), channel)
            except Exception as exc:
                logger.warning("Chatbot runtime falhou: %s", exc)

        return _map_mensagem(mensagem)

    def transferir(self, conversa_id: str, assignee_id: str, actor_name: str) -> dict:
        self._obter_conversa(conversa_id)
        assignee = self._usuario_ativo(assignee_id)
        department = PERFIL_DEPARTAMENTO.get(assignee["role"], "Atendimento")

        row = self.conversas.atualizar(conversa_id, {
            "assigned_to": assignee["id"],
            "department": department,
            "status": "active",
        })
        self._registrar_evento(
            conversa_id,
            f"[Sistema] Atendimento transferido para {assignee['name']} ({department}) por {actor_name}.",
        )
        users = self._users_index()
        return _map_conversa(row or self._obter_conversa(conversa_id), users)

    def assumir(self, conversa_id: str, user_id: str, actor_name: str) -> dict:
        return self.transferir(conversa_id, user_id, actor_name)

    def encerrar(self, conversa_id: str, actor_name: str, note: str | None = None) -> dict:
        self._obter_conversa(conversa_id)
        row = self.conversas.atualizar(conversa_id, {"status": "closed"})
        detail = f" Motivo: {note.strip()}" if note and note.strip() else ""
        self._registrar_evento(
            conversa_id,
            f"[Sistema] Atendimento encerrado por {actor_name}.{detail}",
        )
        users = self._users_index()
        return _map_conversa(row or self._obter_conversa(conversa_id), users)

    def reativar(self, conversa_id: str, actor_name: str) -> dict:
        self._obter_conversa(conversa_id)
        row = self.conversas.atualizar(conversa_id, {"status": "active"})
        self._registrar_evento(
            conversa_id,
            f"[Sistema] Atendimento reaberto por {actor_name}.",
        )
        users = self._users_index()
        return _map_conversa(row or self._obter_conversa(conversa_id), users)

    def reservar_produto(
        self,
        conversa_id: str,
        product_id: str,
        product_name: str,
        actor_name: str,
        quantity: int = 1,
    ) -> dict:
        conversa = self._obter_conversa(conversa_id)
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
        )
        users = self._users_index()
        return _map_conversa(self._obter_conversa(conversa_id), users)

    def contar_conversas(self) -> int:
        try:
            return self.conversas.contar()
        except Exception:
            return 0
