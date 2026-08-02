"""Marca pedidos no Supabase como enviados/entregues para demo TEMPORÁRIA de métricas.

DEPRECATED para produção — use status permanentes no sandbox Mercos (Etapa 4).
Validação: PYTHONPATH=. python scripts/validate_pedidos_mercos.py

Use quando os pedidos no Mercos sandbox ainda estão todos em Processando (status 2).
Após alterar status no Mercos, rode sync — estes valores serão sobrescritos.

Uso:
  PYTHONPATH=. python scripts/demo_pedidos_status.py
  PYTHONPATH=. python scripts/demo_pedidos_status.py --entregues 4 --enviados 2
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.supabase_service import supabase


def main() -> None:
    parser = argparse.ArgumentParser(description="Demo: status de pedidos para Relatórios")
    parser.add_argument("--entregues", type=int, default=4, help="Qtd pedidos com status 4 (entregue)")
    parser.add_argument("--enviados", type=int, default=2, help="Qtd pedidos com status 3 (enviado)")
    args = parser.parse_args()

    res = supabase.table("pedidos").select("mercos_id,numero,situacao,valor_total").order("numero").execute()
    rows = res.data or []
    if not rows:
        print("Nenhum pedido no Supabase — sincronize Mercos antes.")
        return

    entregues = max(0, args.entregues)
    enviados = max(0, args.enviados)
    if entregues + enviados > len(rows):
        print(f"Aviso: só há {len(rows)} pedidos; ajustando quantidades.")
        entregues = min(entregues, len(rows))
        enviados = min(enviados, max(0, len(rows) - entregues))

    print(f"=== Demo status pedidos ({len(rows)} no total) ===\n")

    for i, row in enumerate(rows):
        if i < entregues:
            situacao = "4"
            label = "entregue"
        elif i < entregues + enviados:
            situacao = "3"
            label = "enviado"
        else:
            situacao = "2"
            label = "processando"

        supabase.table("pedidos").update({"situacao": situacao}).eq("mercos_id", row["mercos_id"]).execute()
        print(
            f"  Pedido #{row.get('numero')} -> {label} ({situacao}) | "
            f"R$ {float(row.get('valor_total') or 0):,.2f}"
        )

    print("\nPronto — abra Relatórios no PulseDesk e confira receita retida / funil.")
    print("Para dados permanentes, altere status no sandbox Mercos (Pedidos) e sincronize.")


if __name__ == "__main__":
    main()
