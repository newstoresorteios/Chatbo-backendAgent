from app.core.workspace_scope import apply_workspace_filter, stamp_workspace
from app.services.supabase_service import supabase


class PedidoRepository:

    def salvar(self, pedido: dict, workspace_id: str | None = None):
        payload = stamp_workspace(pedido, workspace_id) if workspace_id else pedido
        on_conflict = "workspace_id,mercos_id" if workspace_id else "mercos_id"
        return (
            supabase
            .table("pedidos")
            .upsert(payload, on_conflict=on_conflict)
            .execute()
        )

    def listar(self, workspace_id: str | None = None) -> list[dict]:
        query = supabase.table("pedidos").select("*")
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        resposta = query.execute()
        return resposta.data or []
