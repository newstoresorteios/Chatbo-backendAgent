from app.core.workspace_scope import apply_workspace_filter
from app.services.supabase_service import supabase


class DashboardRepository:

    def contar_clientes(self, workspace_id: str | None = None):
        query = supabase.table("clientes").select("*", count="exact")
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        return resposta.count

    def contar_produtos(self, workspace_id: str | None = None):
        query = supabase.table("produtos").select("*", count="exact")
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        return resposta.count

    def contar_pedidos(self, workspace_id: str | None = None):
        query = supabase.table("pedidos").select("*", count="exact")
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        return resposta.count
