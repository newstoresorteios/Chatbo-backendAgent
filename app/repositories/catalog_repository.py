from app.services.supabase_service import supabase


class CatalogRepository:
    """Leitura de catálogo sem gravação e limitada ao workspace informado."""

    def contar_produtos(self) -> int:
        resposta = supabase.table("produtos").select("id", count="exact").execute()
        return int(resposta.count or 0)

    def listar_por_workspace(
        self,
        workspace_id: str,
        *,
        search: str | None = None,
        category: str | None = None,
        status: str | None = None,
        page: int = 1,
        limit: int = 25,
    ) -> tuple[list[dict], bool]:
        safe_page = max(page, 1)
        safe_limit = min(max(limit, 1), 100)
        query = (
            supabase.table("produtos")
            .select("*")
            .eq("workspace_id", workspace_id)
            .range((safe_page - 1) * safe_limit, safe_page * safe_limit)
        )
        if search:
            query = query.ilike("nome", f"%{search.strip()}%")
        if category:
            query = query.eq("categoria", category.strip())
        if status == "active":
            query = query.eq("ativo", True)
        elif status == "inactive":
            query = query.eq("ativo", False)
        rows = query.order("nome").execute().data or []
        return rows[:safe_limit], len(rows) > safe_limit

    @staticmethod
    def to_agent_product(row: dict) -> dict:
        stock = row.get("saldo_estoque")
        stock_status = "unknown"
        if isinstance(stock, (int, float)) and not isinstance(stock, bool):
            stock_status = "available" if stock > 0 else "unavailable"
        return {
            "productId": str(row.get("id") or row.get("mercos_id")),
            "name": str(row.get("nome") or "Produto sem nome"),
            "description": row.get("descricao"),
            "price": row.get("preco_tabela"),
            "currency": str(row.get("currency") or "BRL"),
            "availability": "active" if row.get("ativo") is not False else "inactive",
            "stockStatus": stock_status,
            "category": row.get("categoria"),
            "source": "mercos" if row.get("mercos_id") else "catalog",
            "updatedAt": row.get("ultima_alteracao") or row.get("updated_at"),
        }
