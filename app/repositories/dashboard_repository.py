from app.services.supabase_service import supabase


class DashboardRepository:

    def contar_clientes(self):
        resposta = (
            supabase
            .table("clientes")
            .select("*", count="exact")
            .execute()
        )

        return resposta.count

    def contar_produtos(self):
        resposta = (
            supabase
            .table("produtos")
            .select("*", count="exact")
            .execute()
        )

        return resposta.count

    def contar_pedidos(self):
        resposta = (
            supabase
            .table("pedidos")
            .select("*", count="exact")
            .execute()
        )

        return resposta.count