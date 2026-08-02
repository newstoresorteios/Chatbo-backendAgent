"""Remove negócios mock do funil e reconstrói a partir de pedidos/conversas Mercos."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.funil_sync_service import funil_sync_service


def main() -> None:
    print("=== Sync funil com dados Mercos/Supabase ===\n")
    result = funil_sync_service.sincronizar()
    print(result["message"])
    print(f"\n  Removidos (mock): {result['removed']}")
    print(f"  Criados: {result['dealsCreated']}")
    print(f"  Pipeline (pedidos): R$ {result['pipelineValor']:,.2f}")
    print("\nAbra Funil de Vendas e Relatórios no PulseDesk para conferir.")


if __name__ == "__main__":
    main()
