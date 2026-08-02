from app.services.mercos_service import MercosService
from app.repositories.produto_repository import ProdutoRepository
from app.repositories.mercos_sync_repository import MercosSyncRepository


class ProdutoService:
    """Sync Mercos → Supabase: SOMENTE upsert.

    Nunca apaga, nunca inativa produtos automaticamente.
    Catálogo no banco só cresce/atualiza — remoção é ação manual explícita.
    """

    def __init__(self):
        self.mercos = MercosService()
        self.repository = ProdutoRepository()
        self.sync_logs = MercosSyncRepository()

    def sincronizar(self, *, incremental: bool = True):

        alterado_apos = None
        if incremental:
            alterado_apos = self.sync_logs.ultima_sincronizacao("products")

        produtos = self.mercos.listar_produtos(alterado_apos=alterado_apos)

        if isinstance(produtos, dict):
            return produtos

        quantidade = 0

        for produto in produtos:
            dados = {
                "mercos_id": produto.get("id"),
                "nome": produto.get("nome"),
                "codigo": produto.get("codigo"),
                "unidade": produto.get("unidade"),
                "descricao": produto.get("observacoes"),
                "preco_tabela": produto.get("preco_tabela"),
                "preco_minimo": produto.get("preco_minimo"),
                "saldo_estoque": produto.get("saldo_estoque"),
                "ativo": produto.get("ativo"),
                "ultima_alteracao": produto.get("ultima_alteracao"),
            }
            self.repository.salvar(dados)
            quantidade += 1

        cursor = MercosService.max_ultima_alteracao(produtos if isinstance(produtos, list) else [])
        mensagem = (
            f"Produtos sincronizados: {quantidade} "
            f"({'incremental' if alterado_apos else 'completo'}; nenhum apagado)."
        )
        self.sync_logs.registrar(
            tipo="products",
            mensagem=mensagem,
            quantidade=quantidade,
            cursor_ultima_alteracao=cursor,
        )

        return {
            "mensagem": "Sincronização concluída. Nenhum produto foi apagado.",
            "produtos_sincronizados": quantidade,
            "produtos_removidos": 0,
            "incremental": bool(alterado_apos),
            "cursor_ultima_alteracao": cursor,
        }
