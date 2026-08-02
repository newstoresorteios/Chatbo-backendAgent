from datetime import datetime

from app.services.supabase_service import supabase


class BillingRepository:
    def listar_planos_publicos(self) -> list[dict]:
        response = supabase.table("saas_plans").select("*").eq("status", "active").eq("is_public", True).order("sort_order").execute()
        return response.data or []

    def listar_planos(self) -> list[dict]:
        response = supabase.table("saas_plans").select("*").order("sort_order").execute()
        return response.data or []

    def buscar_plano(self, plan_id: str) -> dict | None:
        response = supabase.table("saas_plans").select("*").eq("id", plan_id).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def buscar_plano_por_code(self, code: str) -> dict | None:
        response = supabase.table("saas_plans").select("*").eq("code", code).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def criar_plano(self, payload: dict) -> dict:
        response = supabase.table("saas_plans").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else payload

    def atualizar_plano(self, plan_id: str, payload: dict) -> dict:
        response = supabase.table("saas_plans").update({**payload, "updated_at": datetime.utcnow().isoformat()}).eq("id", plan_id).execute()
        rows = response.data or []
        return rows[0] if rows else {"id": plan_id, **payload}

    def assinatura_corrente(self, workspace_id: str) -> dict | None:
        response = (
            supabase.table("workspace_subscriptions").select("*")
            .eq("workspace_id", workspace_id)
            .in_("status", ["trialing", "active", "past_due", "suspended"])
            .order("created_at", desc=True).limit(1).execute()
        )
        rows = response.data or []
        return rows[0] if rows else None

    def assinatura_por_id(self, subscription_id: str) -> dict | None:
        response = supabase.table("workspace_subscriptions").select("*").eq("id", subscription_id).limit(1).execute()
        rows = response.data or []
        return rows[0] if rows else None

    def listar_assinaturas(self) -> list[dict]:
        response = supabase.table("workspace_subscriptions").select("*").order("created_at", desc=True).execute()
        return response.data or []

    def criar_assinatura(self, payload: dict) -> dict:
        response = supabase.table("workspace_subscriptions").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else payload

    def atualizar_assinatura(self, subscription_id: str, payload: dict) -> dict:
        response = supabase.table("workspace_subscriptions").update({**payload, "updated_at": datetime.utcnow().isoformat()}).eq("id", subscription_id).execute()
        rows = response.data or []
        return rows[0] if rows else {"id": subscription_id, **payload}

    def registrar_evento(self, payload: dict) -> dict:
        response = supabase.table("workspace_subscription_events").insert(payload).execute()
        rows = response.data or []
        return rows[0] if rows else payload

    def uso_periodo(self, workspace_id: str, period_key: str) -> list[dict]:
        response = supabase.table("workspace_usage_counters").select("metric,used_value").eq("workspace_id", workspace_id).eq("period_key", period_key).execute()
        return response.data or []

    def registrar_uso(self, workspace_id: str, metric: str, period_key: str, value: int) -> dict:
        response = (
            supabase.table("workspace_usage_counters")
            .upsert(
                {"workspace_id": workspace_id, "metric": metric, "period_key": period_key, "used_value": value},
                on_conflict="workspace_id,metric,period_key",
            )
            .execute()
        )
        rows = response.data or []
        return rows[0] if rows else {"workspace_id": workspace_id, "metric": metric, "period_key": period_key, "used_value": value}

    def listar_uso(self) -> list[dict]:
        response = supabase.table("workspace_usage_counters").select("workspace_id,metric,period_key,used_value").order("period_key", desc=True).execute()
        return response.data or []
