"""Valida integração WhatsApp (Etapa 5)."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.services.whatsapp_service import whatsapp_service


def main() -> None:
    print("=== ETAPA 5: Validação WhatsApp ===\n")

    status = whatsapp_service.status()
    print(f"Provider: {status.get('provider')}")
    print(f"Configurado: {status.get('configured')}")
    print(f"Conectado: {status.get('connected')}")
    print(f"Status: {status.get('providerStatus')}")
    print(f"Webhook URL: {status.get('webhookUrl')}")
    print(f"Canal ID: {status.get('canalId')}")
    print(f"Mensagem: {status.get('message')}")

    if not status.get("configured"):
        print(
            "\nPENDENTE — Defina no Render:\n"
            "  META_ACCESS_TOKEN\n"
            "  META_PHONE_NUMBER_ID\n"
            "  META_WEBHOOK_VERIFY_TOKEN\n"
            "  META_APP_SECRET (recomendado)\n"
            "  PUBLIC_API_URL=https://xnamai-backendagent.onrender.com"
        )
        return

    test = whatsapp_service.testar_conexao()
    print(f"\nTeste conexão: {'OK' if test.get('ok') else 'FALHA'} — {test.get('message')}")

    if test.get("ok"):
        print("\nOK — Configure o webhook na Meta com a URL acima e envie uma mensagem de teste.")
    else:
        print("\nAVISO — Token ou Phone Number ID inválido.")


if __name__ == "__main__":
    main()
