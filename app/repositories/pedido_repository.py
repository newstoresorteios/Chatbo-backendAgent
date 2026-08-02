from app.services.supabase_service import supabase


class PedidoRepository:

    def salvar(self, pedido: dict):
        return (
            supabase
            .table("pedidos")
            .upsert(pedido, on_conflict="mercos_id")
            .execute()
        )

    def listar(self) -> list[dict]:
        resposta = supabase.table("pedidos").select("*").execute()
        return resposta.data or []
