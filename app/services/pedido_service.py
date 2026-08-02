from app.repositories.mercos_sync_repository import MercosSyncRepository
from app.repositories.pedido_repository import PedidoRepository
from app.config.settings import mercos_ambiente
from app.services.mercos_service import MercosService

SITUACAO_LABELS = {
    "1": "Pendente",
    "2": "Processando",
    "3": "Enviado",
    "4": "Entregue",
    "5": "Cancelado",
}


def _extrair_data_pedido(pedido: dict) -> str | None:
    for key in ("data_emissao", "data_criacao", "data_pedido", "created_at"):
        valor = pedido.get(key)
        if valor:
            return str(valor)
    return None


def _extrair_produto_pedido(pedido: dict) -> tuple[str, str]:
    items = pedido.get("items") or pedido.get("itens") or []
    if not items:
        return "", ""
    item = items[0] if isinstance(items, list) else {}
    if not isinstance(item, dict):
        return "", ""
    nome = (
        item.get("produto_nome")
        or item.get("nome")
        or item.get("descricao")
        or item.get("produto")
        or ""
    )
    codigo = item.get("codigo") or item.get("produto_codigo") or item.get("sku") or ""
    return str(nome).strip(), str(codigo).strip()


def _contar_itens(pedido: dict) -> int:
    items = pedido.get("items") or pedido.get("itens") or []
    if items:
        total = 0
        for item in items:
            try:
                total += int(item.get("quantidade") or 1)
            except (TypeError, ValueError):
                total += 1
        return max(total, len(items))
    try:
        return max(1, int(pedido.get("quantidade_itens") or 1))
    except (TypeError, ValueError):
        return 1


class PedidoService:

    def __init__(self):
        self.mercos = MercosService()
        self.repository = PedidoRepository()
        self.sync_logs = MercosSyncRepository()

    def _mapear_pedido(self, pedido: dict) -> dict:
        produto_nome, produto_codigo = _extrair_produto_pedido(pedido)
        dados = {
            "mercos_id": pedido.get("id"),
            "numero": str(pedido.get("numero") or pedido.get("id") or ""),
            "cliente_mercos_id": pedido.get("cliente_id"),
            "valor_total": pedido.get("total") or 0,
            "situacao": str(pedido.get("status") or "2"),
            "quantidade_itens": _contar_itens(pedido),
            "data_pedido": _extrair_data_pedido(pedido),
            "ultima_alteracao": pedido.get("ultima_alteracao"),
        }
        if produto_nome:
            dados["produto_nome"] = produto_nome
        if produto_codigo:
            dados["produto_codigo"] = produto_codigo
        return dados

    def resumo_situacoes(self) -> dict:
        rows = self.repository.listar()
        breakdown: dict[str, dict] = {}
        retained = 0.0

        for row in rows:
            code = str(row.get("situacao") or "2")
            valor = float(row.get("valor_total") or 0)
            if code not in breakdown:
                breakdown[code] = {
                    "code": code,
                    "label": SITUACAO_LABELS.get(code, code),
                    "count": 0,
                    "value": 0.0,
                }
            breakdown[code]["count"] += 1
            breakdown[code]["value"] += valor
            if code in ("3", "4"):
                retained += valor

        items = sorted(breakdown.values(), key=lambda item: item["code"])
        total = len(rows)
        processing_only = total > 0 and len(items) == 1 and items[0]["code"] == "2"

        return {
            "total": total,
            "breakdown": items,
            "retainedRevenue": round(retained, 2),
            "allOrdersProcessing": processing_only,
        }

    def sincronizar(self, *, incremental: bool = True) -> dict:
        alterado_apos = None
        if incremental:
            alterado_apos = self.sync_logs.ultima_sincronizacao("orders")

        pedidos = self.mercos.listar_pedidos(alterado_apos=alterado_apos)

        if isinstance(pedidos, dict):
            return pedidos

        quantidade = 0

        for pedido in pedidos:
            self.repository.salvar(self._mapear_pedido(pedido))
            quantidade += 1

        resumo = self.resumo_situacoes()
        cursor = MercosService.max_ultima_alteracao(pedidos if isinstance(pedidos, list) else [])
        mensagem = f"Pedidos sincronizados: {quantidade}."
        if resumo["allOrdersProcessing"]:
            alvo = "Mercos" if mercos_ambiente() == "production" else "sandbox Mercos"
            mensagem += (
                f" Todos estão em Processando — altere status no {alvo} "
                "(Pedidos → Enviado/Entregue) e sincronize de novo para métricas permanentes."
            )
        elif resumo["retainedRevenue"] > 0:
            mensagem += f" Receita retida: R$ {resumo['retainedRevenue']:,.2f}.".replace(",", "X").replace(".", ",").replace("X", ".")

        self.sync_logs.registrar(
            tipo="orders",
            mensagem=mensagem,
            quantidade=quantidade,
            resumo=resumo,
            cursor_ultima_alteracao=cursor,
        )

        return {
            "mensagem": mensagem,
            "pedidos_sincronizados": quantidade,
            "resumo": resumo,
            "cursor_ultima_alteracao": cursor,
            "incremental": bool(alterado_apos),
        }
