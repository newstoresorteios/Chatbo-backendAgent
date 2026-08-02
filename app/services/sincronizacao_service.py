from app.services.cliente_service import ClienteService
from app.services.produto_service import ProdutoService
from app.services.pedido_service import PedidoService


class SincronizacaoService:

    def __init__(self):
        self.cliente_service = ClienteService()
        self.produto_service = ProdutoService()
        self.pedido_service = PedidoService()

    def sincronizar_tudo(self):
        clientes = self.cliente_service.sincronizar()
        produtos = self.produto_service.sincronizar()
        pedidos = self.pedido_service.sincronizar()

        return {
            "clientes": clientes,
            "produtos": produtos,
            "pedidos": pedidos,
        }
