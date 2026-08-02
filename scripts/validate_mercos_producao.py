"""Valida configuração Mercos produção (Etapa 6)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.mercos_service import MercosService, mercos_info


def main() -> None:
    print("=== ETAPA 6: Validação Mercos produção ===\n")

    info = mercos_info()
    print(f"Ambiente detectado: {info['environment']}")
    print(f"Host API: {info.get('baseUrlHost')}")
    print(f"Configurado: {info.get('configured')}")
    print(f"Produção: {info.get('isProduction')}")
    print(f"Sandbox: {info.get('isSandbox')}")

    if not info.get("configured"):
        print("\nPENDENTE — Defina MERCOS_APPLICATION_TOKEN, MERCOS_COMPANY_TOKEN e MERCOS_BASE_URL no Render.")
        return

    if info.get("isSandbox"):
        print(
            "\nAVISO — Ainda em SANDBOX.\n"
            "  Para produção, altere no Render:\n"
            "    MERCOS_BASE_URL=https://api.mercos.com/api/v1\n"
            "    MERCOS_APPLICATION_TOKEN=<token produção do cliente>\n"
            "    MERCOS_COMPANY_TOKEN=<company token produção do cliente>\n"
            "    MERCOS_ENV=production  (opcional, força detecção)"
        )

    try:
        clientes = MercosService().listar_clientes()
        if isinstance(clientes, dict):
            print(f"\nFALHA API: {clientes}")
            return
        print(f"\nConexão OK — {len(clientes)} clientes retornados pela API.")
    except Exception as exc:
        print(f"\nFALHA conexão: {exc}")
        return

    if info.get("isProduction"):
        print("\nOK — Mercos PRODUÇÃO respondendo. Use sync com confirmProduction no painel.")
    else:
        print("\nOK — Mercos sandbox respondendo. Troque tokens/URL quando o cliente liberar produção.")


if __name__ == "__main__":
    main()
