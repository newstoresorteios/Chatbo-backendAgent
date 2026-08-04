from app.core.workspace_scope import apply_workspace_filter, stamp_workspace
from app.services.supabase_service import supabase


class ClienteRepository:

    def salvar(self, cliente: dict, workspace_id: str | None = None):
        payload = stamp_workspace(cliente, workspace_id) if workspace_id else cliente
        on_conflict = "workspace_id,mercos_id" if workspace_id else "mercos_id"
        return (
            supabase
            .table("clientes")
            .upsert(
                payload,
                on_conflict=on_conflict,
            )
            .execute()
        )

    def listar_com_telefone(
        self,
        limite: int | None = None,
        workspace_id: str | None = None,
    ) -> list[dict]:
        query = (
            supabase
            .table("clientes")
            .select("mercos_id,nome,razao_social,telefone,celular")
            .order("nome")
        )
        if workspace_id:
            query = apply_workspace_filter(query, workspace_id)
        if limite and limite > 0:
            query = query.limit(limite)
        resposta = query.execute()
        return resposta.data or []