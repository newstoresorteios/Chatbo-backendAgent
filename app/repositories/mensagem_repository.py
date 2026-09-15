from app.services.supabase_service import supabase


class MensagemRepository:

    def ultima_entrada_meta(self, conversa_id: str) -> dict | None:
        rows = (
            supabase.table("mensagens")
            .select("external_id,created_at")
            .eq("conversa_id", conversa_id)
            .eq("sender", "customer")
            .eq("direction", "inbound")
            .like("external_id", "wamid.%")
            .order("created_at", desc=True)
            .limit(1)
            .execute().data or []
        )
        return rows[0] if rows else None

    def listar_por_conversa(
        self,
        conversa_id: str,
        *,
        limit: int | None = None,
        before: str | None = None,
        after: str | None = None,
    ) -> list[dict]:
        query = (
            supabase
            .table("mensagens")
            .select("*")
            .eq("conversa_id", conversa_id)
            .order("created_at", desc=limit is not None)
        )
        if before:
            query = query.lt("created_at", before)
        if after:
            query = query.gt("created_at", after)
        if limit is not None:
            query = query.limit(max(1, min(limit, 200)))
        rows = query.execute().data or []
        return list(reversed(rows)) if limit is not None else rows

    def listar_external_ids(self, conversa_id: str) -> set[str]:
        resposta = (
            supabase
            .table("mensagens")
            .select("external_id")
            .eq("conversa_id", conversa_id)
            .execute()
        )
        return {
            str(row["external_id"])
            for row in (resposta.data or [])
            if row.get("external_id")
        }

    def criar(self, dados: dict) -> dict:
        resposta = supabase.table("mensagens").insert(dados).execute()
        rows = resposta.data or []
        return rows[0] if rows else dados

    def existe_external_id(self, external_id: str) -> bool:
        return bool(self.obter_por_external_id(external_id))

    def obter_por_external_id(self, external_id: str) -> dict | None:
        if not external_id:
            return None
        resposta = (
            supabase
            .table("mensagens")
            .select("*")
            .eq("external_id", external_id)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def reatribuir_conversa(self, mensagem_id: str, conversa_id: str) -> dict | None:
        return self.atualizar(mensagem_id, {"conversa_id": conversa_id})

    def atualizar(self, mensagem_id: str, dados: dict) -> dict | None:
        resposta = (
            supabase
            .table("mensagens")
            .update(dados)
            .eq("id", mensagem_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def atualizar_por_external_id(self, external_id: str, dados: dict) -> dict | None:
        resposta = (
            supabase
            .table("mensagens")
            .update(dados)
            .eq("external_id", external_id)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None
