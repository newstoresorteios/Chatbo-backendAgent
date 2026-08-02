"""Rankings de produtos e clientes com base nos pedidos do Supabase."""

from __future__ import annotations

import logging
import re
from collections import defaultdict

from app.repositories.pedido_repository import PedidoRepository
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

CANCELLED = {"5", "cancelado", "cancelled"}


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _safe_int(value, default: int = 0) -> int:
    try:
        if value is None:
            return default
        return int(value)
    except (TypeError, ValueError):
        return default


def _normalizar_chave(texto: str) -> str:
    return re.sub(r"\s+", " ", (texto or "").strip().lower())


def _extrair_produto_mensagem(conteudo: str) -> str:
    for linha in (conteudo or "").splitlines():
        linha = linha.strip()
        if "📦" in linha:
            return linha.replace("📦", "").strip()
    return ""


class RankingsService:

    def __init__(self):
        self.pedidos_repo = PedidoRepository()

    def _load_pedidos(self) -> list[dict]:
        return self.pedidos_repo.listar()

    def _load_clientes(self) -> list[dict]:
        try:
            resposta = supabase.table("clientes").select("*").execute()
            return resposta.data or []
        except Exception as exc:
            logger.warning("Rankings: falha ao listar clientes: %s", exc)
            return []

    def _load_produtos(self) -> list[dict]:
        try:
            resposta = supabase.table("produtos").select("*").execute()
            return resposta.data or []
        except Exception as exc:
            logger.warning("Rankings: falha ao listar produtos: %s", exc)
            return []

    def _mapa_produto_por_pedido(self) -> dict[str, str]:
        """Fallback: extrai nome do produto das mensagens do agente (pedidos WA-)."""
        resultado: dict[str, str] = {}
        try:
            resposta = (
                supabase.table("mensagens")
                .select("content")
                .eq("direction", "outbound")
                .ilike("content", "%Pedido #%")
                .limit(500)
                .execute()
            )
            for row in resposta.data or []:
                conteudo = row.get("content") or ""
                match = re.search(r"Pedido\s*#(WA-\d+)", conteudo, re.I)
                if not match:
                    continue
                numero = match.group(1).upper()
                produto = _extrair_produto_mensagem(conteudo)
                if produto and numero not in resultado:
                    resultado[numero] = produto
        except Exception as exc:
            logger.warning("Rankings: fallback mensagens indisponível: %s", exc)
        return resultado

    def _nome_cliente(self, cliente_id, clientes_por_id: dict[str, dict]) -> str:
        if cliente_id is None:
            return "Cliente não identificado"
        cliente = clientes_por_id.get(str(cliente_id), {})
        return (
            cliente.get("nome")
            or cliente.get("razao_social")
            or cliente.get("telefone")
            or f"Cliente {cliente_id}"
        )

    def _resolver_produto_pedido(
        self,
        pedido: dict,
        produto_por_numero: dict[str, str],
    ) -> tuple[str, str]:
        nome = (pedido.get("produto_nome") or "").strip()
        codigo = (pedido.get("produto_codigo") or "").strip()
        if nome:
            return nome, codigo

        numero = str(pedido.get("numero") or "").strip().upper()
        if numero in produto_por_numero:
            return produto_por_numero[numero], codigo

        if numero.startswith("WA-"):
            return "Venda WhatsApp", codigo

        return "Produto não informado", codigo

    def _montar_rankings(self, *, limit: int = 10) -> dict:
        pedidos = self._load_pedidos()
        clientes = self._load_clientes()
        catalogo = self._load_produtos()
        produto_por_numero = self._mapa_produto_por_pedido()

        clientes_por_id = {
            str(c.get("mercos_id") or c.get("id")): c for c in clientes
        }

        por_produto: dict[str, dict] = {}
        por_cliente: dict[str, dict] = {}

        pedidos_validos = 0
        for pedido in pedidos:
            situacao = str(pedido.get("situacao") or "").lower()
            if situacao in CANCELLED:
                continue

            pedidos_validos += 1
            valor = _safe_float(pedido.get("valor_total"))
            qtd_itens = max(1, _safe_int(pedido.get("quantidade_itens"), 1))
            cliente_id = pedido.get("cliente_mercos_id")
            produto_nome, produto_codigo = self._resolver_produto_pedido(
                pedido, produto_por_numero
            )
            chave_produto = _normalizar_chave(produto_nome) or "produto-nao-informado"

            if chave_produto not in por_produto:
                por_produto[chave_produto] = {
                    "id": produto_codigo or chave_produto,
                    "code": produto_codigo,
                    "name": produto_nome,
                    "ordersCount": 0,
                    "quantity": 0,
                    "revenue": 0.0,
                }
            por_produto[chave_produto]["ordersCount"] += 1
            por_produto[chave_produto]["quantity"] += qtd_itens
            por_produto[chave_produto]["revenue"] += valor

            chave_cliente = str(cliente_id) if cliente_id is not None else "sem-cliente"
            if chave_cliente not in por_cliente:
                por_cliente[chave_cliente] = {
                    "id": chave_cliente,
                    "name": self._nome_cliente(cliente_id, clientes_por_id),
                    "ordersCount": 0,
                    "revenue": 0.0,
                    "lastOrderAt": pedido.get("data_pedido") or pedido.get("created_at"),
                }
            por_cliente[chave_cliente]["ordersCount"] += 1
            por_cliente[chave_cliente]["revenue"] += valor
            data_pedido = pedido.get("data_pedido") or pedido.get("created_at")
            if data_pedido and (not por_cliente[chave_cliente]["lastOrderAt"] or data_pedido > por_cliente[chave_cliente]["lastOrderAt"]):
                por_cliente[chave_cliente]["lastOrderAt"] = data_pedido

        produtos_vendidos = sorted(
            por_produto.values(),
            key=lambda item: (-item["ordersCount"], -item["revenue"], item["name"]),
        )

        for produto in catalogo:
            nome = (produto.get("nome") or "").strip()
            if not nome:
                continue
            chave = _normalizar_chave(nome)
            if chave in por_produto:
                continue
            por_produto[chave] = {
                "id": str(produto.get("mercos_id") or produto.get("id") or produto.get("codigo") or chave),
                "code": produto.get("codigo") or "",
                "name": nome,
                "ordersCount": 0,
                "quantity": 0,
                "revenue": 0.0,
            }

        todos_produtos = sorted(
            por_produto.values(),
            key=lambda item: (item["ordersCount"], item["revenue"], item["name"]),
        )

        clientes_compradores = sorted(
            por_cliente.values(),
            key=lambda item: (-item["ordersCount"], -item["revenue"], item["name"]),
        )

        for cliente in clientes:
            cid = str(cliente.get("mercos_id") or cliente.get("id"))
            if cid in por_cliente:
                continue
            por_cliente[cid] = {
                "id": cid,
                "name": cliente.get("nome") or cliente.get("razao_social") or cid,
                "ordersCount": 0,
                "revenue": 0.0,
                "lastOrderAt": None,
            }

        todos_clientes = sorted(
            por_cliente.values(),
            key=lambda item: (item["ordersCount"], item["revenue"], item["name"]),
        )

        return {
            "produtosMaisVendidos": produtos_vendidos[:limit],
            "produtosMenosVendidos": todos_produtos[:limit],
            "clientesMaisCompram": clientes_compradores[:limit],
            "clientesMenosCompram": todos_clientes[:limit],
            "totals": {
                "pedidos": pedidos_validos,
                "produtosComVenda": sum(1 for p in por_produto.values() if p["ordersCount"] > 0),
                "clientesComPedido": sum(1 for c in por_cliente.values() if c["ordersCount"] > 0),
                "produtosCatalogo": len(catalogo),
                "clientesCadastro": len(clientes),
            },
        }

    def rankings(self, *, limit: int = 10) -> dict:
        try:
            return self._montar_rankings(limit=max(3, min(limit, 50)))
        except Exception as exc:
            logger.exception("Erro ao calcular rankings: %s", exc)
            return {
                "produtosMaisVendidos": [],
                "produtosMenosVendidos": [],
                "clientesMaisCompram": [],
                "clientesMenosCompram": [],
                "totals": {
                    "pedidos": 0,
                    "produtosComVenda": 0,
                    "clientesComPedido": 0,
                    "produtosCatalogo": 0,
                    "clientesCadastro": 0,
                },
            }


rankings_service = RankingsService()
