from app.services.supabase_service import supabase


TRACE_COLUMNS = (
    "id,inbound_id,workspace_id,channel,intent,handoff_required,safety_reason,"
    "provider_send_ok,provider_response,created_at"
)


class AgentTraceRepository:
    def listar(
        self,
        workspace_id: str,
        *,
        limit: int,
        before: str | None = None,
        channel: str | None = None,
        delivered: bool | None = None,
        handoff: bool | None = None,
    ) -> list[dict]:
        query = (
            supabase.table("ai_agent_responses")
            .select(TRACE_COLUMNS)
            .eq("workspace_id", workspace_id)
            .order("created_at", desc=True)
            .limit(limit + 1)
        )
        if before:
            query = query.lt("created_at", before)
        if channel:
            query = query.eq("channel", channel)
        if delivered is not None:
            query = query.eq("provider_send_ok", delivered)
        if handoff is not None:
            query = query.eq("handoff_required", handoff)
        return query.execute().data or []

    def obter(self, response_id: int, workspace_id: str) -> dict | None:
        rows = (
            supabase.table("ai_agent_responses")
            .select(TRACE_COLUMNS)
            .eq("id", response_id)
            .eq("workspace_id", workspace_id)
            .limit(1)
            .execute()
            .data
            or []
        )
        return rows[0] if rows else None
