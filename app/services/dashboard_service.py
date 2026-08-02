from collections import defaultdict
from datetime import datetime, timedelta

from app.repositories.conversa_repository import ConversaRepository
from app.repositories.dashboard_repository import DashboardRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.services.openai_provider import openai_configured
from app.services.supabase_service import supabase

MESES_PT = ("Jan", "Fev", "Mar", "Abr", "Mai", "Jun", "Jul", "Ago", "Set", "Out", "Nov", "Dez")


def _parse_date(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00")).replace(tzinfo=None)
    except ValueError:
        return None


def _day_key(dt: datetime) -> str:
    return dt.strftime("%d/%m")


def _contar_por_dia(rows: list[dict], date_field: str, days: int = 7) -> dict[str, int]:
    hoje = datetime.utcnow().date()
    inicio = hoje - timedelta(days=days - 1)
    buckets: dict[str, int] = defaultdict(int)

    for row in rows:
        dt = _parse_date(row.get(date_field))
        if not dt:
            continue
        dia = dt.date()
        if inicio <= dia <= hoje:
            buckets[_day_key(dt)] += 1

    return buckets


def _labels_ultimos_dias(days: int = 7) -> list[str]:
    hoje = datetime.utcnow().date()
    return [
        _day_key(datetime.combine(hoje - timedelta(days=i), datetime.min.time()))
        for i in range(days - 1, -1, -1)
    ]


def _formatar_tempo_resposta(minutos: float) -> str:
    if minutos <= 0:
        return "—"
    if minutos < 1:
        return f"{int(minutos * 60)}s"
    mins = int(minutos)
    segs = int((minutos - mins) * 60)
    if segs:
        return f"{mins}m {segs}s"
    return f"{mins}min"


def _calcular_tempos_resposta(mensagens: list[dict]) -> list[float]:
    por_conversa: dict[str, list[dict]] = defaultdict(list)
    for msg in mensagens:
        por_conversa[str(msg.get("conversa_id"))].append(msg)

    deltas: list[float] = []
    for msgs in por_conversa.values():
        ordenadas = sorted(msgs, key=lambda m: m.get("created_at") or "")
        for i, msg in enumerate(ordenadas):
            if msg.get("sender") != "customer":
                continue
            for prox in ordenadas[i + 1 :]:
                if prox.get("sender") in {"agent", "ai"}:
                    t1 = _parse_date(msg.get("created_at"))
                    t2 = _parse_date(prox.get("created_at"))
                    if t1 and t2 and t2 > t1:
                        deltas.append((t2 - t1).total_seconds() / 60)
                    break
    return deltas


def _calcular_tempo_resposta_medio(mensagens: list[dict]) -> str:
    deltas = _calcular_tempos_resposta(mensagens)
    if not deltas:
        return "—"
    return _formatar_tempo_resposta(sum(deltas) / len(deltas))


def _chart_pedidos_mensal(pedidos_rows: list[dict], months: int = 6) -> list[dict]:
    hoje = datetime.utcnow()
    buckets: dict[tuple[int, int], int] = defaultdict(int)

    for row in pedidos_rows:
        dt = _parse_date(row.get("created_at"))
        if not dt:
            continue
        buckets[(dt.year, dt.month)] += 1

    chart: list[dict] = []
    for offset in range(months - 1, -1, -1):
        month_dt = hoje.replace(day=1)
        year, month = month_dt.year, month_dt.month - offset
        while month <= 0:
            month += 12
            year -= 1
        count = buckets.get((year, month), 0)
        chart.append(
            {
                "name": MESES_PT[month - 1],
                "conversas": 0,
                "pedidos": count,
                "clientes": 0,
            }
        )
    return chart


def _chart_tempo_resposta_horario(mensagens: list[dict]) -> list[dict]:
    por_conversa: dict[str, list[dict]] = defaultdict(list)
    for msg in mensagens:
        por_conversa[str(msg.get("conversa_id"))].append(msg)

    por_hora: dict[int, list[float]] = defaultdict(list)

    for msgs in por_conversa.values():
        ordenadas = sorted(msgs, key=lambda m: m.get("created_at") or "")
        for i, msg in enumerate(ordenadas):
            if msg.get("sender") != "customer":
                continue
            t1 = _parse_date(msg.get("created_at"))
            if not t1:
                continue
            for prox in ordenadas[i + 1 :]:
                if prox.get("sender") in {"agent", "ai"}:
                    t2 = _parse_date(prox.get("created_at"))
                    if t2 and t2 > t1:
                        por_hora[t1.hour].append((t2 - t1).total_seconds() / 60)
                    break

    horas = sorted(set(range(8, 19)) | set(por_hora.keys()))
    if not horas:
        horas = list(range(8, 19))

    chart: list[dict] = []
    for hora in horas:
        valores = por_hora.get(hora, [])
        media = round(sum(valores) / len(valores), 1) if valores else 0
        chart.append(
            {
                "name": f"{hora:02d}h",
                "conversas": media,
                "pedidos": 0,
                "clientes": 0,
            }
        )
    return chart


def _contar_campanhas_enviadas() -> int:
    try:
        resposta = supabase.table("campanhas").select("sent").execute()
        return sum(int(row.get("sent") or 0) for row in (resposta.data or []))
    except Exception:
        return 0


class DashboardService:

    def __init__(self):
        self.repository = DashboardRepository()
        self.conversas = ConversaRepository()
        self.mensagens = MensagemRepository()

    def resumo(self):
        return {
            "clientes": self.repository.contar_clientes(),
            "produtos": self.repository.contar_produtos(),
            "pedidos": self.repository.contar_pedidos(),
        }

    def _contar_conversas_por_status(self) -> dict[str, int]:
        try:
            rows = self.conversas.listar()
        except Exception:
            return {"active": 0, "waiting": 0, "closed": 0}

        counts = {"active": 0, "waiting": 0, "closed": 0}
        for row in rows:
            status = row.get("status") or "active"
            if status in counts:
                counts[status] += 1
        return counts

    def _carregar_linhas(self, tabela: str, campo_data: str = "created_at") -> list[dict]:
        try:
            resposta = supabase.table(tabela).select(campo_data).execute()
            return resposta.data or []
        except Exception:
            return []

    def _stats_mensagens(self) -> dict:
        try:
            resposta = supabase.table("mensagens").select("sender,conversa_id,created_at").execute()
            rows = resposta.data or []
        except Exception:
            return {"total": 0, "ai": 0, "bot_pct": 0, "avg_response": "—", "rows": []}

        total = len(rows)
        ai = sum(1 for r in rows if r.get("sender") == "ai")
        bot_pct = round((ai / total) * 100) if total else 0
        return {
            "total": total,
            "ai": ai,
            "bot_pct": bot_pct,
            "avg_response": _calcular_tempo_resposta_medio(rows),
            "rows": rows,
        }

    def montar(self) -> dict:
        status = self._contar_conversas_por_status()
        msg_stats = self._stats_mensagens()

        clientes_rows = self._carregar_linhas("clientes")
        pedidos_rows = self._carregar_linhas("pedidos")
        conversas_rows = self._carregar_linhas("conversas", "last_message_at")
        if not conversas_rows:
            conversas_rows = self._carregar_linhas("conversas", "created_at")

        clientes_dia = _contar_por_dia(clientes_rows, "created_at")
        pedidos_dia = _contar_por_dia(pedidos_rows, "created_at")
        conversas_dia = _contar_por_dia(conversas_rows, "last_message_at")
        if not any(conversas_dia.values()):
            conversas_dia = _contar_por_dia(conversas_rows, "created_at")

        labels = _labels_ultimos_dias()
        conversations_chart = [
            {
                "name": label,
                "conversas": conversas_dia.get(label, 0),
                "pedidos": pedidos_dia.get(label, 0),
                "clientes": clientes_dia.get(label, 0),
            }
            for label in labels
        ]

        total_clientes = self.repository.contar_clientes() or 0
        total_produtos = self.repository.contar_produtos() or 0
        total_pedidos = self.repository.contar_pedidos() or 0
        total_conversas = sum(status.values())

        return {
            "stats": {
                "activeConversations": status["active"],
                "closedConversations": status["closed"],
                "waitingQueue": status["waiting"],
                "avgResponseTime": msg_stats["avg_response"],
                "aiOnline": openai_configured(),
                "campaignsSent": _contar_campanhas_enviadas(),
                "botResolved": msg_stats["bot_pct"],
                "totalCustomers": total_clientes,
                "totalProducts": total_produtos,
                "totalOrders": total_pedidos,
                "totalMessages": msg_stats["total"],
            },
            "conversationsChart": conversations_chart,
            "ordersChart": _chart_pedidos_mensal(pedidos_rows),
            "responseTimeChart": _chart_tempo_resposta_horario(msg_stats.get("rows") or []),
        }
