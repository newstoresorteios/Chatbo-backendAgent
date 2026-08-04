from app.services.cliente_service import ClienteService
from app.services.produto_service import ProdutoService
from app.services.pedido_service import PedidoService


class SincronizacaoService:

    def __init__(self):
        self.cliente_service = ClienteService()
        self.produto_service = ProdutoService()
        self.pedido_service = PedidoService()

    def sincronizar_tudo(self, workspace_id: str | None = None):
        clientes = self.cliente_service.sincronizar(workspace_id=workspace_id)
        produtos = self.produto_service.sincronizar(workspace_id=workspace_id)
        pedidos = self.pedido_service.sincronizar(workspace_id=workspace_id)

        return {
            "clientes": clientes,
            "produtos": produtos,
            "pedidos": pedidos,
        }
