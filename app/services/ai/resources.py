"""Factory de services AI por tabela."""

from __future__ import annotations

from app.repositories.ai.workspace_crud import WorkspaceCrudRepository
from app.services.ai.workspace_crud_service import WorkspaceCrudService


def _svc(
    table: str,
    *,
    id_column: str = "id",
    workspace_column: str | None = "workspace_id",
    order_by: str = "created_at",
    order_desc: bool = True,
    touch_updated_at: bool = True,
) -> WorkspaceCrudService:
    return WorkspaceCrudService(
        WorkspaceCrudRepository(
            table,
            id_column=id_column,
            workspace_column=workspace_column,
            order_by=order_by,
            order_desc=order_desc,
            touch_updated_at=touch_updated_at,
        )
    )


# Messages
inbound_messages_service = _svc("ai_inbound_messages", touch_updated_at=False)
agent_responses_service = _svc("ai_agent_responses", touch_updated_at=False)

# Preferences / memory
user_preferences_service = _svc("ai_user_preferences", order_by="updated_at")
contact_memories_service = _svc("ai_contact_memories", order_by="updated_at")
conversation_summaries_service = _svc("ai_conversation_summaries", order_by="updated_at")
memory_proposals_service = _svc("ai_memory_proposals", touch_updated_at=False)

# Remarketing
remarketing_contacts_service = _svc("ai_remarketing_contacts", order_by="updated_at")
conversation_statuses_service = _svc("ai_conversation_statuses", order_by="updated_at")
remarketing_attempts_service = _svc("ai_remarketing_attempts", order_by="updated_at")

# Identity / commerce / pix
identity_links_service = _svc("ai_customer_identity_links", order_by="updated_at")
commerce_sessions_service = _svc(
    "ai_customer_commerce_sessions",
    id_column="person_key",
    order_by="updated_at",
)
pix_payments_service = _svc("ai_pix_payments", order_by="updated_at")

# Persona runtime AI
persona_versions_service = _svc("ai_agent_persona_versions", order_by="created_at", touch_updated_at=False)
instruction_extensions_service = _svc("ai_agent_instruction_extensions", order_by="updated_at")
prompt_compilations_service = _svc("ai_prompt_compilations", touch_updated_at=False)

# CRM gaps
leads_service = _svc("leads", order_by="updated_at")
coupon_users_service = _svc(
    "users",
    workspace_column=None,
    order_by="created_at",
    touch_updated_at=True,
)
