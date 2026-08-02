"""Valida contexto do Copiloto com dados reais (Etapa 7)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.agent_context_builder import AgentContextBuilder
from app.services.conversas_service import ConversasService


def main() -> None:
    print("=== ETAPA 7: Validação Copiloto ===\n")

    conversas = ConversasService().listar_conversas()
    print(f"Conversas: {len(conversas)}")

    builder = AgentContextBuilder()
    conv_id = conversas[0]["id"] if conversas else None
    customer_id = conversas[0].get("customerId") if conversas else None

    ctx = builder.build(conv_id, customer_id, user_message="status do pedido e metricas de venda")

    stats = ctx.get("platformStats") or {}
    metrics = ctx.get("salesMetrics") or {}
    orders = ctx.get("orders") or []
    products = ctx.get("products") or []

    print(f"Cliente: {(ctx.get('customer') or {}).get('name', 'N/A')}")
    print(f"Pedidos do cliente no contexto: {len(orders)}")
    print(f"Produtos relevantes: {len(products)}")
    print(f"Plataforma — clientes: {stats.get('clientes', 0)}, produtos: {stats.get('produtos', 0)}, pedidos: {stats.get('pedidos', 0)}")
    print(f"Métricas — vendas: {metrics.get('quantidadeVendas', 0)}, retido: R$ {float(metrics.get('valorRetido') or 0):,.2f}")

    prompt = builder.to_prompt(ctx)
    print(f"\nPrompt gerado: {len(prompt)} caracteres")

    ok = bool(metrics) or stats.get("pedidos", 0) > 0
    print("\n" + ("OK — Copiloto tem dados reais para responder" if ok else "AVISO — sync Mercos ou seed conversas antes de testar"))


if __name__ == "__main__":
    main()
