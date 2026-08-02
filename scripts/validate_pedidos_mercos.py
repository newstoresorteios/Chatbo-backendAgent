"""Valida pedidos Mercos permanentes no Supabase (etapa 4).

Confirma mix de status (enviado/entregue) e receita retida após sync do sandbox.
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.pedido_service import PedidoService
from app.services.vendas_service import vendas_service


def main() -> None:
    print("=== ETAPA 4: Validação pedidos Mercos permanentes ===\n")

    resumo = PedidoService().resumo_situacoes()
    print(f"Total pedidos no Supabase: {resumo['total']}")

    if resumo["total"] == 0:
        print("\nAVISO — Nenhum pedido. Sincronize Mercos antes (Configurações → Mercos).")
        return

    print("\nStatus (fonte: Mercos sandbox → sync → Supabase):")
    for item in resumo["breakdown"]:
        print(
            f"  {item['label']} ({item['code']}): {item['count']} pedidos | "
            f"R$ {item['value']:,.2f}"
        )

    print(f"\nReceita retida (enviado + entregue): R$ {resumo['retainedRevenue']:,.2f}")

    if resumo["allOrdersProcessing"]:
        print(
            "\nAVISO — Todos os pedidos estão em Processando (status 2).\n"
            "  1. Abra o sandbox Mercos → Pedidos\n"
            "  2. Marque 2–4 pedidos como Enviado (3) ou Entregue (4)\n"
            "  3. PulseDesk → Configurações → Mercos → Sincronizar Pedidos\n"
            "  Não use demo_pedidos_status.py — o sync sobrescreve patches locais."
        )
    else:
        print("\nOK — Há pedidos com status avançado (permanentes após re-sync).")

    metricas = vendas_service.metricas()
    print(f"\nMétricas Relatórios:")
    print(f"  Concluídos: {metricas['quantidadeConcluidas']}")
    print(f"  Valor retido: R$ {metricas['valorRetido']:,.2f}")
    print(f"  Taxa retenção: {metricas['taxaRetencao']}%")

    ok = resumo["retainedRevenue"] > 0 or not resumo["allOrdersProcessing"]
    print("\n" + ("OK — dados prontos para Relatórios/Funil/Copiloto" if ok else "PENDENTE — ajuste status no Mercos sandbox"))


if __name__ == "__main__":
    main()
