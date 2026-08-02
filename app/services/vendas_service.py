import logging
from collections import defaultdict
from datetime import datetime, timedelta

from app.repositories.conversa_repository import ConversaRepository
from app.repositories.platform_repository import PlatformRepository
from app.services.pulsedesk_adapter import listar_pedidos

logger = logging.getLogger(__name__)


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _sum_total(items: list[dict]) -> float:
    return sum(_safe_float(i.get("total")) for i in items)


def _pct(part: float, whole: float, cap: float = 100.0) -> float:
    if not whole:
        return 0.0
    return min(cap, round((part / whole) * 100, 1))


class VendasService:

    def __init__(self):
        self.conversas = ConversaRepository()
        self.platform = PlatformRepository()

    def _load_pedidos(self) -> list[dict]:
        try:
            resp = listar_pedidos(page=1, page_size=500)
            return resp.get("data") or []
        except Exception:
            return []

    def _load_funil(self) -> list[dict]:
        try:
            estagios = self.platform.list_estagios()
            negocios = self.platform.list_negocios()
        except Exception:
            return []

        por_estagio: dict[str, list[dict]] = defaultdict(list)
        for negocio in negocios:
            por_estagio[str(negocio.get("stage_id"))].append(negocio)

        return [
            {
                "id": estagio["id"],
                "name": estagio["name"],
                "sortOrder": int(estagio.get("sort_order") or 0),
                "dealsCount": len(por_estagio.get(str(estagio["id"]), [])),
                "dealsValue": sum(_safe_float(n.get("value")) for n in por_estagio.get(str(estagio["id"]), [])),
            }
            for estagio in sorted(estagios, key=lambda e: int(e.get("sort_order") or 0))
        ]

    def _vendas_por_dia(self, pedidos: list[dict], days: int = 30) -> list[dict]:
        hoje = datetime.utcnow().date()
        inicio = hoje - timedelta(days=days - 1)
        buckets: dict[str, dict] = {}

        for i in range(days):
            dia = hoje - timedelta(days=days - 1 - i)
            key = dia.strftime("%d/%m")
            buckets[key] = {"name": key, "vendas": 0, "valor": 0.0}

        for pedido in pedidos:
            if pedido.get("status") == "cancelled":
                continue
            dt = _parse_date(pedido.get("createdAt"))
            if not dt or dt.date() < inicio or dt.date() > hoje:
                continue
            key = dt.strftime("%d/%m")
            if key in buckets:
                buckets[key]["vendas"] += 1
                buckets[key]["valor"] += _safe_float(pedido.get("total"))

        return list(buckets.values())

    def _montar_funil(
        self,
        *,
        conversas_total: int,
        funil_estagios: list[dict],
        pipeline_valor: float,
        pipeline_qtd: int,
        pedidos_total: int,
        volume_bruto: float,
        shipped: list[dict],
        delivered: list[dict],
        valor_retido: float,
    ) -> list[dict]:
        """Funil sequencial: contato → oportunidade → pedido → envio → receita."""
        etapas: list[dict] = []

        if conversas_total:
            etapas.append({
                "id": "conversas",
                "label": "Contatos / Conversas",
                "quantidade": conversas_total,
                "valor": 0.0,
                "tipo": "topo",
            })

        if pipeline_qtd:
            etapas.append({
                "id": "oportunidades",
                "label": "Oportunidades no funil",
                "quantidade": pipeline_qtd,
                "valor": round(pipeline_valor, 2),
                "tipo": "funil",
            })

        for estagio in funil_estagios:
            if estagio["dealsCount"] <= 0:
                continue
            etapas.append({
                "id": str(estagio["id"]),
                "label": estagio["name"],
                "quantidade": estagio["dealsCount"],
                "valor": round(estagio["dealsValue"], 2),
                "tipo": "funil",
            })

        etapas.extend([
            {
                "id": "pedidos-confirmados",
                "label": "Pedidos confirmados",
                "quantidade": pedidos_total,
                "valor": round(volume_bruto, 2),
                "tipo": "pedido",
            },
            {
                "id": "pedidos-enviados",
                "label": "Enviados / em trânsito",
                "quantidade": len(shipped),
                "valor": round(_sum_total(shipped), 2),
                "tipo": "pedido",
            },
            {
                "id": "pedidos-entregues",
                "label": "Entregues (receita retida)",
                "quantidade": len(delivered),
                "valor": round(valor_retido, 2),
                "tipo": "receita",
            },
        ])

        if not etapas:
            return []

        topo_qtd = max(int(etapas[0].get("quantidade") or 0), 1)
        prev_qtd = topo_qtd
        for etapa in etapas:
            qtd = int(etapa.get("quantidade") or 0)
            etapa["conversaoPct"] = _pct(qtd, topo_qtd)
            etapa["quedaPct"] = _pct(qtd, prev_qtd)
            prev_qtd = max(qtd, 1)

        return etapas

    def _metricas_vazias(self) -> dict:
        return {
            "quantidadeVendas": 0,
            "quantidadeConcluidas": 0,
            "quantidadeEntregues": 0,
            "valorTotalVendido": 0.0,
            "valorConcluido": 0.0,
            "volumeBruto": 0.0,
            "valorRetido": 0.0,
            "valorPipeline": 0.0,
            "valorCancelado": 0.0,
            "ticketMedio": 0.0,
            "taxaConversao": 0.0,
            "taxaRetencao": 0.0,
            "pipelineNegocios": 0,
            "pipelineValor": 0.0,
            "funil": [],
            "porStatus": [],
            "vendasPorDia": [],
        }

    def metricas(self) -> dict:
        try:
            return self._calcular_metricas()
        except Exception as exc:
            logger.exception("Erro ao calcular métricas de venda: %s", exc)
            return self._metricas_vazias()

    def _calcular_metricas(self) -> dict:
        pedidos = self._load_pedidos()
        funil_estagios = self._load_funil()

        by_status: dict[str, list[dict]] = defaultdict(list)
        for pedido in pedidos:
            by_status[pedido.get("status") or "pending"].append(pedido)

        delivered = by_status["delivered"]
        shipped = by_status["shipped"]
        processing = by_status["processing"]
        pending = by_status["pending"]
        cancelled = by_status["cancelled"]

        vendas_concluidas = delivered + shipped
        em_processamento = pending + processing
        pedidos_validos = [p for p in pedidos if p.get("status") != "cancelled"]

        volume_bruto = _sum_total(pedidos_validos)
        valor_retido = _sum_total(delivered)
        valor_concluido = _sum_total(vendas_concluidas)
        valor_total_vendido = volume_bruto
        valor_pipeline = _sum_total(em_processamento)
        valor_cancelado = _sum_total(cancelled)

        quantidade_vendas = len(pedidos_validos)
        quantidade_concluidas = len(vendas_concluidas)
        quantidade_entregues = len(delivered)
        ticket_medio = valor_total_vendido / quantidade_vendas if quantidade_vendas else 0

        try:
            conversas = self.conversas.listar()
            conversas_total = len(conversas)
        except Exception:
            conversas_total = 0

        pipeline_valor = sum(s.get("dealsValue", 0) for s in funil_estagios)
        pipeline_qtd = sum(s.get("dealsCount", 0) for s in funil_estagios)

        etapas_funil = self._montar_funil(
            conversas_total=conversas_total,
            funil_estagios=funil_estagios,
            pipeline_valor=pipeline_valor,
            pipeline_qtd=pipeline_qtd,
            pedidos_total=quantidade_vendas,
            volume_bruto=volume_bruto,
            shipped=shipped,
            delivered=delivered,
            valor_retido=valor_retido,
        )

        if conversas_total:
            taxa_conversao = _pct(quantidade_entregues, conversas_total)
        elif quantidade_vendas:
            taxa_conversao = _pct(quantidade_entregues, quantidade_vendas)
        else:
            taxa_conversao = 0.0

        taxa_retencao = _pct(valor_retido, volume_bruto)

        return {
            "quantidadeVendas": quantidade_vendas,
            "quantidadeConcluidas": quantidade_concluidas,
            "quantidadeEntregues": quantidade_entregues,
            "valorTotalVendido": round(valor_total_vendido, 2),
            "valorConcluido": round(valor_concluido, 2),
            "volumeBruto": round(volume_bruto, 2),
            "valorRetido": round(valor_retido, 2),
            "valorPipeline": round(valor_pipeline, 2),
            "valorCancelado": round(valor_cancelado, 2),
            "ticketMedio": round(ticket_medio, 2),
            "taxaConversao": taxa_conversao,
            "taxaRetencao": taxa_retencao,
            "pipelineNegocios": pipeline_qtd,
            "pipelineValor": round(pipeline_valor, 2),
            "funil": etapas_funil,
            "porStatus": [
                {
                    "status": "delivered",
                    "label": "Entregues",
                    "quantidade": len(delivered),
                    "valor": round(_sum_total(delivered), 2),
                },
                {
                    "status": "shipped",
                    "label": "Enviados",
                    "quantidade": len(shipped),
                    "valor": round(_sum_total(shipped), 2),
                },
                {
                    "status": "processing",
                    "label": "Processando",
                    "quantidade": len(processing),
                    "valor": round(_sum_total(processing), 2),
                },
                {
                    "status": "pending",
                    "label": "Pendentes",
                    "quantidade": len(pending),
                    "valor": round(_sum_total(pending), 2),
                },
                {
                    "status": "cancelled",
                    "label": "Cancelados",
                    "valor": round(valor_cancelado, 2),
                    "quantidade": len(cancelled),
                },
            ],
            "vendasPorDia": self._vendas_por_dia(pedidos),
        }


vendas_service = VendasService()
