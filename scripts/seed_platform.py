"""Popula canais, funil, campanhas, chatbot e integrações iniciais no Supabase."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.data.platform_seed import (
    SEED_CAMPAIGNS,
    SEED_CHANNELS,
    SEED_CHATBOTS,
    SEED_FUNNEL,
    SEED_INTEGRATIONS,
)
from app.repositories.platform_repository import PlatformRepository
from app.services.supabase_service import supabase


def _tabelas_existem() -> bool:
    try:
        supabase.table("canais").select("id").limit(0).execute()
        supabase.table("funil_estagios").select("id").limit(0).execute()
        supabase.table("integracoes").select("id").limit(0).execute()
        return True
    except Exception:
        return False


def main():
    if not _tabelas_existem():
        print("Tabelas da plataforma nao existem.")
        print("Execute primeiro: supabase/003_platform.sql no SQL Editor do Supabase")
        print("Ou: python scripts/apply_platform_schema.py (com SUPABASE_DB_URL no .env)")
        sys.exit(1)

    repo = PlatformRepository()

    if repo.count_canais() > 0:
        print(f"Ja existem {repo.count_canais()} canais. Seed ignorado.")
        return

    for i, channel in enumerate(SEED_CHANNELS):
        repo.create_canal({
            "id": channel["id"],
            "type": channel["type"],
            "name": channel["name"],
            "connected": channel.get("connected", True),
            "messages_today": channel.get("messagesToday", 0),
            "phone": channel.get("phone"),
            "last_activity": channel.get("lastActivity"),
        })
    print(f"Criados {len(SEED_CHANNELS)} canais.")

    for i, stage in enumerate(SEED_FUNNEL):
        repo.create_estagio({
            "id": stage["id"],
            "name": stage["name"],
            "sort_order": i,
        })
        for deal in stage.get("deals", []):
            repo.create_negocio({
                "id": deal["id"],
                "stage_id": deal["stageId"],
                "title": deal["title"],
                "contact": deal["contact"],
                "value": deal["value"],
                "channel": deal["channel"],
            })
    print(f"Criados {len(SEED_FUNNEL)} estagios do funil.")

    for campaign in SEED_CAMPAIGNS:
        dados = {
            "id": campaign["id"],
            "name": campaign["name"],
            "channel": campaign["channel"],
            "status": campaign["status"],
            "recipients": campaign.get("recipients", 0),
            "sent": campaign.get("sent", 0),
            "opened": campaign.get("opened", 0),
        }
        if campaign.get("scheduledAt"):
            dados["scheduled_at"] = campaign["scheduledAt"]
        repo.create_campanha(dados)
    print(f"Criadas {len(SEED_CAMPAIGNS)} campanhas.")

    for flow in SEED_CHATBOTS:
        repo.create_chatbot({
            "id": flow["id"],
            "name": flow["name"],
            "channel": flow["channel"],
            "active": flow.get("active", True),
            "triggers": flow.get("triggers", 0),
            "resolved": flow.get("resolved", 0),
        })
    print(f"Criados {len(SEED_CHATBOTS)} fluxos de chatbot.")

    for item in SEED_INTEGRATIONS:
        repo.create_integracao({
            "id": item["id"],
            "name": item["name"],
            "category": item["category"],
            "connected": item.get("connected", False),
        })
    print(f"Criadas {len(SEED_INTEGRATIONS)} integracoes.")

    print("\nPronto. Canais, funil, campanhas, robo e integracoes persistem no Supabase.")


if __name__ == "__main__":
    main()
