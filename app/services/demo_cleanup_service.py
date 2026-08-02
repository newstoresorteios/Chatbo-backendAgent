"""Remove dados de demonstração (seed) do Supabase."""

from __future__ import annotations

import logging

from app.data.platform_seed import (
    SEED_CAMPAIGNS,
    SEED_CHANNELS,
    SEED_CHATBOTS,
    SEED_INTEGRATIONS,
)
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

SENTINEL_ID = "00000000-0000-0000-0000-000000000000"

SEED_CHANNEL_IDS = [c["id"] for c in SEED_CHANNELS]
SEED_CAMPAIGN_IDS = [c["id"] for c in SEED_CAMPAIGNS]
SEED_CHATBOT_IDS = [c["id"] for c in SEED_CHATBOTS]
SEED_INTEGRATION_IDS = [i["id"] for i in SEED_INTEGRATIONS if i["id"] != "mercos"]

MERCOS_TABLES = ("pedidos", "clientes", "produtos")


def _count(table: str) -> int:
    res = supabase.table(table).select("*", count="exact").limit(1).execute()
    if hasattr(res, "count") and res.count is not None:
        return res.count
    return len(res.data or [])


def _delete_by_ids(table: str, ids: list[str]) -> int:
    for row_id in ids:
        supabase.table(table).delete().eq("id", row_id).execute()
    return len(ids)


def _delete_all(table: str) -> int:
    before = _count(table)
    if before == 0:
        return 0
    supabase.table(table).delete().neq("id", SENTINEL_ID).execute()
    after = _count(table)
    if after > 0 and table not in ("conversas", "mensagens"):
        logger.warning("Tabela %s: restaram %s registros após limpeza", table, after)
    return before


def _ensure_mercos_integration() -> None:
    res = supabase.table("integracoes").select("id").eq("id", "mercos").limit(1).execute()
    if res.data:
        supabase.table("integracoes").update({
            "connected": False,
            "name": "Mercos",
            "category": "erp",
        }).eq("id", "mercos").execute()
        return
    supabase.table("integracoes").insert({
        "id": "mercos",
        "name": "Mercos",
        "category": "erp",
        "connected": False,
    }).execute()


def limpar_demo(*, incluir_mercos: bool = False) -> dict:
    antes = {
        "conversas": _count("conversas"),
        "campanhas": _count("campanhas"),
        "canais": _count("canais"),
        "chatbot_fluxos": _count("chatbot_fluxos"),
        "integracoes": _count("integracoes"),
        "funil_negocios": _count("funil_negocios"),
        "clientes": _count("clientes"),
        "produtos": _count("produtos"),
        "pedidos": _count("pedidos"),
    }

    removidos = {
        "conversas": _delete_all("conversas"),
        "campanhas": _delete_by_ids("campanhas", SEED_CAMPAIGN_IDS),
        "canais": _delete_by_ids("canais", SEED_CHANNEL_IDS),
        "chatbot_fluxos": _delete_by_ids("chatbot_fluxos", SEED_CHATBOT_IDS),
        "integracoes": _delete_by_ids("integracoes", SEED_INTEGRATION_IDS),
        "funil_negocios": _delete_all("funil_negocios"),
    }

    if incluir_mercos:
        for table in MERCOS_TABLES:
            removidos[table] = _delete_all(table)

    _ensure_mercos_integration()

    depois = {
        "conversas": _count("conversas"),
        "campanhas": _count("campanhas"),
        "canais": _count("canais"),
        "chatbot_fluxos": _count("chatbot_fluxos"),
        "integracoes": _count("integracoes"),
        "funil_negocios": _count("funil_negocios"),
        "clientes": _count("clientes"),
        "produtos": _count("produtos"),
        "pedidos": _count("pedidos"),
    }

    return {
        "success": True,
        "message": (
            "Dados de demonstração removidos. Sincronize o Mercos para carregar dados reais."
            if not incluir_mercos
            else "Demo e dados Mercos antigos removidos. Sincronize a conta nova no Mercos."
        ),
        "removed": removidos,
        "before": antes,
        "after": depois,
    }
