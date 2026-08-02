"""Remove dados de demonstração (seed) e prepara o Supabase para usar só Mercos."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.demo_cleanup_service import limpar_demo


def main() -> None:
    parser = argparse.ArgumentParser(description="Limpa dados de demo do PulseDesk")
    parser.add_argument(
        "--incluir-mercos",
        action="store_true",
        help="Também remove clientes, produtos e pedidos (antes de sync nova conta)",
    )
    args = parser.parse_args()

    print("=== Limpeza dados de demonstração (PulseDesk) ===\n")
    result = limpar_demo(incluir_mercos=args.incluir_mercos)

    print("Antes:", result["before"])
    print("\nRemovidos:", result["removed"])
    print("\nDepois:", result["after"])
    print(f"\n{result['message']}")
    print("\nPróximos passos:")
    print("1. Render: tokens Mercos")
    print("2. Configuracoes -> Mercos -> Testar + Sincronizar")
    print("3. Funil -> Sincronizar do Mercos")


if __name__ == "__main__":
    main()
