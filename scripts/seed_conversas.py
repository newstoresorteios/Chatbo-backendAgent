"""Popula conversas e mensagens iniciais no Supabase."""

import sys
from copy import deepcopy
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.repositories.conversa_repository import ConversaRepository
from app.repositories.mensagem_repository import MensagemRepository
from app.services.supabase_service import supabase

CONVERSAS_INICIAIS = [
    {
        "cliente_mercos_id": "9255263",
        "customer_name": "Carlos Mendes",
        "last_message": "Preciso do modelo Pro-X500, cerca de 50 unidades.",
        "status": "active",
        "unread_count": 2,
        "channel": "whatsapp",
        "department": "Comercial",
        "protocol": "PD-2024-8841",
        "assigned_to": "Ana Silva",
        "mensagens": [
            ("Olá, bom dia! Preciso de um orçamento.", "customer"),
            ("Olá Carlos! Claro, posso ajudar. Qual produto você precisa?", "ai"),
            ("Preciso do modelo Pro-X500, cerca de 50 unidades.", "customer"),
        ],
    },
    {
        "cliente_mercos_id": "9255310",
        "customer_name": "Mariana Costa",
        "last_message": "Obrigada pelo atendimento!",
        "status": "closed",
        "unread_count": 0,
        "channel": "instagram",
        "department": "Suporte",
        "protocol": "PD-2024-8839",
        "mensagens": [
            ("Obrigada pelo atendimento!", "customer"),
        ],
    },
    {
        "cliente_mercos_id": "9255314",
        "customer_name": "Roberto Alves",
        "last_message": "Quando chega meu pedido #4521?",
        "status": "waiting",
        "unread_count": 1,
        "channel": "whatsapp",
        "department": "Logística",
        "protocol": "PD-2024-8835",
        "mensagens": [
            ("Quando chega meu pedido #4521?", "customer"),
        ],
    },
]


def _tabelas_existem() -> bool:
    try:
        supabase.table("conversas").select("id").limit(0).execute()
        supabase.table("mensagens").select("id").limit(0).execute()
        return True
    except Exception:
        return False


def main():
    if not _tabelas_existem():
        print("Tabelas conversas/mensagens nao existem.")
        print("Execute primeiro: supabase/001_conversas_mensagens.sql no SQL Editor do Supabase")
        print("Ou: python scripts/apply_conversas_schema.py (com SUPABASE_DB_URL no .env)")
        sys.exit(1)

    conversa_repo = ConversaRepository()
    mensagem_repo = MensagemRepository()

    existentes = conversa_repo.listar()
    if existentes:
        print(f"Ja existem {len(existentes)} conversas. Seed ignorado.")
        return

    base = datetime.utcnow()

    for i, item in enumerate(CONVERSAS_INICIAIS):
        dados = deepcopy(item)
        mensagens = dados.pop("mensagens")
        dados["last_message_at"] = (base - timedelta(hours=i + 1)).isoformat()

        conversa = conversa_repo.criar(dados)
        conversa_id = conversa["id"]

        for j, (content, sender) in enumerate(mensagens):
            mensagem_repo.criar({
                "conversa_id": conversa_id,
                "content": content,
                "sender": sender,
                "status": "read",
            })

        print(f"Criada conversa: {dados['customer_name']} ({conversa_id})")

    print("\nPronto. Abra Atendimento no PulseDesk para ver as conversas.")


if __name__ == "__main__":
    main()
