from app.services.supabase_service import supabase


class ProdutoRepository:
    """Persistência de produtos. Sync só faz upsert — nunca DELETE."""

    def salvar(self, produto: dict):
        return (
            supabase
            .table("produtos")
            .upsert(
                produto,
                on_conflict="mercos_id",
            )
            .execute()
        )
