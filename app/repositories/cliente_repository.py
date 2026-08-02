from app.services.supabase_service import supabase


class ClienteRepository:

    def salvar(self, cliente: dict):

        return (
            supabase
            .table("clientes")
            .upsert(
                cliente,
                on_conflict="mercos_id"
            )
            .execute()
        )

    def listar_com_telefone(self, limite: int | None = None) -> list[dict]:
        query = (
            supabase
            .table("clientes")
            .select("mercos_id,nome,razao_social,telefone,celular")
            .order("nome")
        )
        if limite and limite > 0:
            query = query.limit(limite)
        resposta = query.execute()
        return resposta.data or []