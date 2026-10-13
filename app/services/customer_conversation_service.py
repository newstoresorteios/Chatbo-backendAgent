"""Open a customer's WhatsApp contact in the central inbox without sending a message."""
from datetime import datetime, timezone
from uuid import UUID
from fastapi import HTTPException
from app.repositories.conversa_repository import ConversaRepository
from app.services.contact_inbox_service import ContactInboxService, map_contact
from app.services.customer_phone import whatsapp_phone
from app.services.inbox_cache import invalidate_conversa
from app.services.supabase_service import supabase


class CustomerConversationService:
    def open(self, customer_id: str, workspace_id: str, actor_id: str) -> dict:
        rows = []
        try:
            UUID(customer_id)
        except ValueError:
            pass
        else:
            rows = (supabase.table("clientes").select("*").eq("workspace_id", workspace_id)
                    .eq("id", customer_id).limit(1).execute().data or [])
        if not rows:
            # Older Mercos lists expose the Mercos ID instead of the database UUID.
            if customer_id.isdigit():
                rows = (supabase.table("clientes").select("*").eq("workspace_id", workspace_id)
                        .eq("mercos_id", int(customer_id)).limit(1).execute().data or [])
        if not rows:
            raise HTTPException(404, "Cliente não encontrado nesta empresa")
        customer = rows[0]
        phone = whatsapp_phone(customer.get("celular")) or whatsapp_phone(customer.get("telefone"))
        if not phone:
            raise HTTPException(400, "Cliente sem telefone válido para WhatsApp")
        repo = ConversaRepository()
        conversation = None
        identities = [phone, "+" + phone, "whatsapp:" + phone]
        if phone.startswith("55"):
            identities.append(phone[2:])
        for identity in identities:
            conversation = repo.obter_por_contato(identity, workspace_id=workspace_id, channel="whatsapp")
            if conversation:
                break
        if not conversation:
            conversation = repo.criar({
                "cliente_id": str(customer["id"]), "cliente_mercos_id": customer.get("mercos_id"),
                "customer_name": customer.get("nome") or customer.get("razao_social") or "Cliente",
                "channel": "whatsapp", "contact_phone": phone, "external_thread_id": phone,
                "status": "active", "assigned_to": actor_id, "bot_activated": False,
                "last_message": "", "last_message_at": datetime.now(timezone.utc).isoformat(),
                "unread_count": 0,
            }, workspace_id=workspace_id)
        invalidate_conversa(str(conversation["id"]), workspace_id)
        inbox = ContactInboxService()
        return map_contact(inbox.obter(str(conversation["id"]), workspace_id), inbox.sessions._users_index())


customer_conversation_service = CustomerConversationService()
