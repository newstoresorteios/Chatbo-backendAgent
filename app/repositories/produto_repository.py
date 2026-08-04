from app.core.workspace_scope import stamp_workspace
from app.services.supabase_service import supabase


class ProdutoRepository:
    """Persistência de produtos. Sync só faz upsert — nunca DELETE."""

    def salvar(self, produto: dict, workspace_id: str | None = None):
        payload = stamp_workspace(produto, workspace_id) if workspace_id else produto
        on_conflict = "workspace_id,mercos_id" if workspace_id else "mercos_id"
        return (
            supabase
            .table("produtos")
            .upsert(
                payload,
                on_conflict=on_conflict,
            )
            .execute()
        )
