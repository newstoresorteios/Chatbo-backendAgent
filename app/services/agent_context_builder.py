import logging
import re
import unicodedata
from datetime import datetime

logger = logging.getLogger(__name__)

from app.repositories.dashboard_repository import DashboardRepository
from app.services.agent_knowledge import full_knowledge_base
from app.services.conversas_service import ConversasService
from app.services.pulsedesk_adapter import listar_clientes, listar_pedidos, listar_produtos, obter_cliente
from app.services.vendas_service import vendas_service


def _format_currency(value: float) -> str:
    return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")


def _safe_float(value, default: float = 0.0) -> float:
    try:
        if value is None:
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def _normalize(text: str) -> str:
    text = unicodedata.normalize("NFD", (text or "").lower())
    return "".join(c for c in text if unicodedata.category(c) != "Mn")


class AgentContextBuilder:
    def __init__(self):
        self.conversas = ConversasService()
        self.dashboard = DashboardRepository()

    def build(
        self,
        conversation_id: str | None = None,
        customer_id: str | None = None,
        history: list[dict] | None = None,
        user_message: str | None = None,
    ) -> dict:
        conversation = None
        conversation_messages: list[dict] = []
        session_messages: list[dict] = []
        all_conversations: list[dict] = []

        try:
            all_conversations = self.conversas.listar_conversas()
        except Exception:
            all_conversations = []

        if conversation_id:
            conversation = next((c for c in all_conversations if c["id"] == conversation_id), None)
            if conversation:
                customer_id = customer_id or conversation.get("customerId")
                try:
                    conversation_messages = self.conversas.listar_mensagens(conversation_id)
                except Exception:
                    conversation_messages = []

        if history:
            for i, item in enumerate(history):
                role = item.get("role", "user")
                session_messages.append({
                    "id": f"h-{i}",
                    "conversationId": conversation_id or "",
                    "content": item.get("content", ""),
                    "sender": "customer" if role == "user" else "ai",
                    "timestamp": datetime.utcnow().isoformat(),
                    "status": "read",
                })

        messages = conversation_messages + session_messages

        search_text = " ".join(filter(None, [
            user_message or "",
            *(m.get("content", "") for m in session_messages if m.get("sender") == "customer"),
            *(m.get("content", "") for m in conversation_messages if m.get("sender") == "customer"),
        ]))

        if not customer_id:
            customer_id = self._resolve_customer_id(search_text, all_conversations)

        customer = None
        customer_detail = None
        orders: list[dict] = []
        if customer_id:
            try:
                customer = obter_cliente(str(customer_id))
                if customer:
                    customer_detail = dict(customer)
                    orders = list(customer.get("orders") or [])
                    if not orders:
                        orders = self._load_orders_for_customer(str(customer_id), customer.get("name"))
                    customer["ordersCount"] = len(orders)
                    customer["totalSpent"] = sum(_safe_float(o.get("total")) for o in orders)
                    customer_detail["orders"] = orders[:10]
            except Exception:
                customer = None
                customer_detail = None
                orders = []

        try:
            products = self._load_relevant_products(search_text)
        except Exception:
            products = []

        try:
            related_orders = self._search_orders(search_text, orders)
        except Exception:
            related_orders = orders[:3]

        last_customer_msg = None
        for msg in reversed(conversation_messages):
            if msg.get("sender") == "customer":
                last_customer_msg = msg.get("content")
                break
        if not last_customer_msg:
            for msg in reversed(session_messages):
                if msg.get("sender") == "customer":
                    last_customer_msg = msg.get("content")
                    break
        if not last_customer_msg and conversation:
            last_customer_msg = conversation.get("lastMessage")

        products_catalog = self._format_catalog(products)
        platform_stats = self._platform_stats()
        sales_metrics = self._load_sales_metrics()
        recent_orders = self._load_recent_orders()

        return {
            "conversation": conversation,
            "allConversations": all_conversations[:8],
            "customer": customer,
            "customerDetail": customer_detail,
            "messages": messages,
            "conversationMessages": conversation_messages,
            "sessionHistory": session_messages,
            "lastCustomerMessage": last_customer_msg,
            "productsCatalog": products_catalog,
            "products": products,
            "orders": orders[:10],
            "relatedOrders": related_orders,
            "recentOrders": recent_orders,
            "platformStats": platform_stats,
            "salesMetrics": sales_metrics,
            "userMessage": user_message,
        }

    def _load_orders_for_customer(self, customer_id: str, customer_name: str | None = None) -> list[dict]:
        matched: list[dict] = []
        search_terms = [customer_id]
        if customer_name:
            search_terms.append(customer_name.split()[0])

        seen: set[str] = set()
        for term in search_terms:
            try:
                resp = listar_pedidos(page=1, page_size=200, search=term)
                for order in resp.get("data") or []:
                    if str(order.get("customerId")) != str(customer_id):
                        continue
                    oid = str(order.get("id") or order.get("number") or "")
                    if oid and oid not in seen:
                        seen.add(oid)
                        matched.append(order)
            except Exception:
                continue
        return matched

    def _resolve_customer_id(self, text: str, conversations: list[dict]) -> str | None:
        norm = _normalize(text)
        for conv in conversations:
            name = _normalize(conv.get("customerName") or "")
            if name and len(name) > 4 and name in norm:
                return conv.get("customerId")
            first = name.split(" ")[0] if name else ""
            if first and len(first) > 3 and first in norm:
                return conv.get("customerId")

        words = [w for w in re.findall(r"[a-záàâãéêíóôõúç]{4,}", norm) if w not in _STOP_WORDS]
        for word in words[:3]:
            try:
                result = listar_clientes(page=1, page_size=5, search=word)
                items = result.get("data") or []
                if items:
                    return items[0].get("id")
            except Exception:
                continue
        return None

    def _load_relevant_products(self, search_text: str) -> list[dict]:
        terms = self._extract_search_terms(search_text)
        found: dict[str, dict] = {}

        for term in terms[:4]:
            try:
                resp = listar_produtos(page=1, page_size=15, search=term)
                for p in resp.get("data") or []:
                    found[str(p.get("id"))] = p
            except Exception:
                continue

        if len(found) < 20:
            try:
                resp = listar_produtos(page=1, page_size=40)
                for p in resp.get("data") or []:
                    found[str(p.get("id"))] = p
            except Exception:
                pass

        return list(found.values())[:40]

    def _extract_search_terms(self, text: str) -> list[str]:
        norm = _normalize(text)
        terms = []
        for code in re.findall(r"\b[a-z]{0,3}-?\d{2,5}\b", norm):
            if len(code) >= 3:
                terms.append(code)
        for word in re.findall(r"[a-záàâãéêíóôõúç]{4,}", norm):
            if word not in _STOP_WORDS:
                terms.append(word)
        return terms

    def _search_orders(self, text: str, customer_orders: list[dict]) -> list[dict]:
        nums = re.findall(r"#?(\d{3,})", text or "")
        if not nums:
            return customer_orders[:3]

        pools: list[dict] = list(customer_orders)
        try:
            pedidos_resp = listar_pedidos(page=1, page_size=200)
            pools.extend(pedidos_resp.get("data") or [])
        except Exception:
            pass

        matched = []
        seen: set[str] = set()
        for num in nums:
            for order in pools:
                if num not in str(order.get("number", "")):
                    continue
                oid = str(order.get("id") or order.get("number") or "")
                if oid and oid not in seen:
                    seen.add(oid)
                    matched.append(order)
        return matched or customer_orders[:3]

    def _format_catalog(self, products: list[dict]) -> str:
        if not products:
            return "Nenhum produto sincronizado — oriente sync Mercos em Configurações."
        return "\n".join(
            f"- {p.get('code')} | {p.get('name')} | {_format_currency(_safe_float(p.get('price')))} | "
            f"estoque: {p.get('stock', 0)} un. | categoria: {p.get('category', 'Geral')}"
            for p in products
        )

    def _platform_stats(self) -> dict:
        try:
            stats = {
                "clientes": self.dashboard.contar_clientes() or 0,
                "produtos": self.dashboard.contar_produtos() or 0,
                "pedidos": self.dashboard.contar_pedidos() or 0,
            }
            try:
                from app.repositories.mercos_sync_repository import MercosSyncRepository

                sync_repo = MercosSyncRepository()
                stats["lastMercosSync"] = (
                    sync_repo.ultima_sincronizacao("orders")
                    or sync_repo.ultima_sincronizacao("all")
                )
            except Exception:
                stats["lastMercosSync"] = None
            return stats
        except Exception:
            return {"clientes": 0, "produtos": 0, "pedidos": 0, "lastMercosSync": None}

    def _load_sales_metrics(self) -> dict:
        try:
            return vendas_service.metricas()
        except Exception as exc:
            logger.warning("Falha ao carregar métricas de venda: %s", exc)
            return {}

    def _load_recent_orders(self, limit: int = 25) -> list[dict]:
        try:
            resp = listar_pedidos(page=1, page_size=limit)
            return resp.get("data") or []
        except Exception:
            return []

    def _format_sales_metrics(self, metrics: dict) -> str:
        if not metrics:
            return "Métricas de venda indisponíveis — verifique pedidos e sync Mercos."

        lines = [
            f"- Pedidos confirmados (vendas): {metrics.get('quantidadeVendas', 0)}",
            f"- Enviados/entregues: {metrics.get('quantidadeConcluidas', 0)} | Entregues: {metrics.get('quantidadeEntregues', 0)}",
            f"- Valor total vendido: {_format_currency(_safe_float(metrics.get('valorTotalVendido')))}",
            f"- Valor concluído (enviado+entregue): {_format_currency(_safe_float(metrics.get('valorConcluido')))}",
            f"- Volume bruto: {_format_currency(_safe_float(metrics.get('volumeBruto')))}",
            f"- Receita retida (entregues): {_format_currency(_safe_float(metrics.get('valorRetido')))}",
            f"- Pipeline em aberto: {_format_currency(_safe_float(metrics.get('valorPipeline')))}",
            f"- Cancelados: {_format_currency(_safe_float(metrics.get('valorCancelado')))}",
            f"- Ticket médio: {_format_currency(_safe_float(metrics.get('ticketMedio')))}",
            f"- Taxa conversão (contato→entrega): {metrics.get('taxaConversao', 0)}%",
            f"- Taxa retenção (retido/bruto): {metrics.get('taxaRetencao', 0)}%",
            f"- Oportunidades no funil: {metrics.get('pipelineNegocios', 0)} | "
            f"{_format_currency(_safe_float(metrics.get('pipelineValor')))}",
        ]

        funil = metrics.get("funil") or []
        if funil:
            lines.append("")
            lines.append("#### Funil de vendas (etapas)")
            for step in funil:
                valor = (
                    _format_currency(_safe_float(step.get("valor")))
                    if _safe_float(step.get("valor")) > 0
                    else "—"
                )
                lines.append(
                    f"- {step.get('label')}: {step.get('quantidade', 0)} un. | {valor} | "
                    f"{step.get('conversaoPct', 0)}% do topo"
                )

        por_status = metrics.get("porStatus") or []
        if por_status:
            lines.append("")
            lines.append("#### Pedidos por status")
            for item in por_status:
                if item.get("quantidade", 0) > 0 or _safe_float(item.get("valor")) > 0:
                    lines.append(
                        f"- {item.get('label')}: {item.get('quantidade', 0)} | "
                        f"{_format_currency(_safe_float(item.get('valor')))}"
                    )

        return "\n".join(lines)

    def to_prompt(self, ctx: dict) -> str:
        intent = detect_intent(ctx)
        lines = [
            full_knowledge_base(),
            "",
            "## Dados em tempo real (prioridade máxima — use estes números)",
        ]

        stats = ctx.get("platformStats") or {}
        lines.extend([
            "",
            "### Plataforma",
            f"- Clientes cadastrados: {stats.get('clientes', 0)}",
            f"- Produtos no catálogo: {stats.get('produtos', 0)}",
            f"- Pedidos registrados: {stats.get('pedidos', 0)}",
        ])
        if stats.get("lastMercosSync"):
            lines.append(f"- Última sync Mercos (pedidos): {stats.get('lastMercosSync')}")
        elif stats.get("pedidos", 0) == 0:
            lines.append("- Aviso: nenhum pedido no Supabase — sincronize Mercos em Configurações.")

        sales = ctx.get("salesMetrics") or {}
        if sales:
            lines.extend([
                "",
                "### Métricas de venda (Relatórios — use estes números para perguntas sobre vendas, funil e receita)",
                self._format_sales_metrics(sales),
            ])

        conv = ctx.get("conversation")
        if conv:
            lines.extend([
                "",
                "### Conversa ativa",
                f"- Cliente: {conv.get('customerName')}",
                f"- ID cliente Mercos: {conv.get('customerId') or 'N/A'}",
                f"- Canal: {conv.get('channel')} | Status: {conv.get('status')}",
                f"- Protocolo: {conv.get('protocol') or 'N/A'} | Depto: {conv.get('department') or 'N/A'}",
                f"- Atribuído a: {conv.get('assignedTo') or 'N/A'}",
                f"- Não lidas: {conv.get('unreadCount', 0)}",
                f"- Intenção detectada: {intent}",
                f"- Última mensagem: {conv.get('lastMessage')}",
            ])

        all_conv = ctx.get("allConversations") or []
        if all_conv and not conv:
            lines.append("")
            lines.append("### Conversas recentes")
            for c in all_conv[:5]:
                lines.append(
                    f"- {c.get('customerName')} ({c.get('channel')}): {str(c.get('lastMessage', ''))[:80]}"
                )

        customer = ctx.get("customer")
        if customer:
            lines.extend([
                "",
                "### Cliente (CRM / Mercos)",
                f"- Nome: {customer.get('name')}",
                f"- Empresa: {customer.get('company')}",
                f"- E-mail: {customer.get('email') or 'N/A'}",
                f"- Telefone: {customer.get('phone') or 'N/A'}",
                f"- Cidade: {customer.get('city') or 'N/A'}",
                f"- Pedidos: {customer.get('ordersCount', 0)} | Lifetime: {_format_currency(_safe_float(customer.get('totalSpent')))}",
            ])

        for label, order_list in [
            ("Pedidos do cliente", ctx.get("orders") or []),
            ("Pedidos mencionados na pergunta", ctx.get("relatedOrders") or []),
        ]:
            if order_list:
                lines.append("")
                lines.append(f"### {label}")
                for order in order_list[:8]:
                    lines.append(
                        f"- Nº {order.get('number')} | status: {order.get('status')} | "
                        f"{_format_currency(_safe_float(order.get('total')))} | "
                        f"{order.get('items', 1)} itens | cliente: {order.get('customerName') or '—'}"
                    )

        recent_orders = ctx.get("recentOrders") or []
        if recent_orders:
            lines.append("")
            lines.append("### Pedidos recentes na plataforma")
            for order in recent_orders[:15]:
                lines.append(
                    f"- Nº {order.get('number')} | {order.get('customerName') or 'Cliente'} | "
                    f"status: {order.get('status')} | {_format_currency(_safe_float(order.get('total')))}"
                )

        conv_msgs = ctx.get("conversationMessages") or []
        if conv_msgs:
            lines.append("")
            lines.append("### Historico da conversa com o cliente (canal real)")
            for msg in conv_msgs[-15:]:
                who = "Cliente" if msg.get("sender") == "customer" else "Atendente/IA"
                lines.append(f"{who}: {msg.get('content', '')[:500]}")

        session = ctx.get("sessionHistory") or []
        if session:
            lines.append("")
            lines.append("### Historico do chat com o Copiloto (sessao de teste do atendente)")
            for msg in session[-15:]:
                who = "Atendente" if msg.get("sender") == "customer" else "Copiloto"
                lines.append(f"{who}: {msg.get('content', '')[:500]}")

        if not conv_msgs and not session:
            messages = ctx.get("messages") or []
            if messages:
                lines.append("")
                lines.append("### Historico recente")
                for msg in messages[-12:]:
                    sender = msg.get("sender")
                    who = "Atendente" if sender == "customer" else "Copiloto"
                    lines.append(f"{who}: {msg.get('content', '')[:500]}")

        lines.extend([
            "",
            "### Catálogo de produtos (relevante para esta pergunta)",
            ctx.get("productsCatalog") or "Sem produtos.",
        ])

        user_msg = ctx.get("userMessage") or ""
        if user_msg and detect_intent(ctx, user_msg) == "sales_metrics":
            lines.extend([
                "",
                "### Instrução para esta pergunta (métricas/funil)",
                "- Interprete os números: o que está indo bem, onde há gargalo, o que priorizar.",
                "- Diferencie pedidos Mercos (vendas reais) de oportunidades CRM (pipeline).",
                "- Cite valores exatos do contexto; não liste todas as etapas sem explicar.",
            ])

        return "\n".join(lines)


_STOP_WORDS = {
    "para", "como", "qual", "quando", "onde", "sobre", "preciso", "quero", "pode",
    "cliente", "conversa", "resuma", "sugira", "liste", "mensagem", "resposta",
    "copiloto", "pulse", "desk", "relatorio", "relatorios", "esta", "quais",
}


def detect_intent(ctx: dict, message: str | None = None) -> str:
    parts = [
        message or "",
        ctx.get("lastCustomerMessage") or "",
        ctx.get("userMessage") or "",
        *(m.get("content", "") for m in ctx.get("messages", []) if m.get("sender") == "customer"),
    ]
    norm = _normalize(" ".join(parts))

    if re.search(r"urgente|suporte urgente|imediato|reclam", norm):
        return "urgent_support"
    if re.search(r"orcamento|cotacao|preco|valor|unidades|desconto", norm):
        return "quote"
    if re.search(r"pedido|entrega|rastreio|chega|prazo", norm):
        return "tracking"
    if re.search(r"estoque|disponivel|produto|catalogo", norm):
        return "stock"
    if re.search(r"visita|tecnica|agendar|instalacao|manutencao", norm):
        return "technical_visit"
    if re.search(r"proposta|analisar|recebi|negoci", norm):
        return "proposal_followup"
    if re.search(r"garantia|troca|devolu", norm):
        return "warranty"
    if re.search(r"pagamento|parcel|boleto|pix|credito", norm):
        return "payment"
    if re.search(r"obrigad|excelente|otimo atendimento", norm):
        return "closed_positive"
    if re.search(
        r"vendas?|vendemos|vendido|faturamento|receita|retenc|retido|metricas?|"
        r"funil|pipeline comercial|ticket medio|conversao|volume bruto|"
        r"quanto vend|quantas vend|pedidos confirmados|relatorio",
        norm,
    ):
        return "sales_metrics"
    return "general"


def _first_name(ctx: dict) -> str:
    customer = ctx.get("customer") or {}
    conv = ctx.get("conversation") or {}
    name = customer.get("name") or conv.get("customerName") or ""
    return name.split(" ")[0] if name else ""


def _find_product(ctx: dict, text: str) -> dict | None:
    norm = _normalize(text)
    for product in ctx.get("products") or []:
        code = _normalize(product.get("code") or "")
        pname = _normalize(product.get("name") or "")
        if code and code in norm:
            return product
        if pname and pname in norm:
            return product
        for part in pname.split():
            if len(part) > 3 and part in norm:
                return product
    return None


def _extract_quantity(text: str) -> int | None:
    match = re.search(r"(\d+)\s*(unidades?|un\.?|pcs?|pecas?)?", text, re.I)
    return int(match.group(1)) if match else None


def _find_order(ctx: dict, text: str) -> dict | None:
    related = ctx.get("relatedOrders") or []
    if related:
        return related[0]

    orders = ctx.get("orders") or []
    if orders:
        return orders[0]

    detail = ctx.get("customerDetail") or {}
    detail_orders = detail.get("orders") or []
    if detail_orders:
        return detail_orders[0]

    pools: list[dict] = []
    pools.extend(detail_orders)
    pools.extend(orders)
    try:
        pedidos_resp = listar_pedidos(page=1, page_size=200)
        pools.extend(pedidos_resp.get("data") or [])
    except Exception:
        pass
    pools.extend(ctx.get("recentOrders") or [])

    seen: set[str] = set()
    all_orders: list[dict] = []
    for order in pools:
        oid = str(order.get("id") or order.get("number") or "")
        if oid and oid not in seen:
            seen.add(oid)
            all_orders.append(order)

    num_match = re.search(r"#?(\d{1,})", text or "")
    if num_match:
        num = num_match.group(1)
        for order in all_orders:
            if num in str(order.get("number", "")):
                return order

    customer_id = (ctx.get("customer") or {}).get("id")
    if customer_id:
        for order in all_orders:
            if str(order.get("customerId")) == str(customer_id):
                return order

    return None
