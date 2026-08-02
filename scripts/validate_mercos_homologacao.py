"""Checklist técnico para homologação Mercos (sandbox → produção)."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from dotenv import load_dotenv

load_dotenv()

from app.services.mercos_service import MercosService  # noqa: E402


def main() -> None:
    print("=== Homologação Mercos — PulseDesk ===\n")
    relatorio = MercosService().status_homologacao()
    print(json.dumps(relatorio, ensure_ascii=False, indent=2))

    print("\n--- Proximos passos ---")
    print("1. Sandbox Mercos: menu Homologacao beta, rodar testes")
    print("2. PulseDesk Integracoes: sincronizar clientes, produtos e pedidos")
    print("3. Enviar prints/evidencias ao suporte Mercos")
    print("4. Reuniao de homologacao (throttling 429 + paginacao alterado_apos)")
    print("5. Apos aprovacao, trocar tokens/URL para producao no Render")

    if relatorio.get("prontoParaHomologacao"):
        print("\nOK — critérios técnicos principais atendidos no backend.")
    else:
        print("\nPENDENTE — corrija erros acima antes da reunião de homologação.")
        sys.exit(1)


if __name__ == "__main__":
    main()
