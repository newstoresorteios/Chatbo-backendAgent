"""Reconstrói o pipeline CRM (funil_negocios) a partir de pedidos e conversas reais."""

import logging

from app.repositories.conversa_repository import ConversaRepository
from app.repositories.platform_repository import PlatformRepository
from app.services.pulsedesk_adapter import listar_pedidos

logger = logging.getLogger(__name__)

SENTINEL_ID = "00000000-0000-0000-0000-000000000000"

DEFAULT_STAGES = [
    ("s1", "Lead", 0),
    ("s2", "Qualificação", 1),
    ("s3", "Proposta", 2),
    ("s4", "Negociação", 3),
    ("s5", "Fechado", 4),
]

ORDER_STAGE_BY_STATUS = {
    "pending": "s1",
    "processing": "s3",
    "shipped": "s4",
    "delivered": "s5",
}


class FunilSyncService:

    def __init__(self):
        self.repo = PlatformRepository()
        self.conversas = ConversaRepository()

    def _ensure_stages(self) -> None:
        existing = {e["id"] for e in self.repo.list_estagios()}
        for stage_id, name, sort_order in DEFAULT_STAGES:
            if stage_id not in existing:
                self.repo.create_estagio({
                    "id": stage_id,
                    "name": name,
                    "sort_order": sort_order,
                })

    def _clear_negocios(self) -> int:
        from app.services.supabase_service import supabase

        res = supabase.table("funil_negocios").select("*", count="exact").limit(1).execute()
        before = res.count if hasattr(res, "count") and res.count is not None else len(res.data or [])
        if before:
            supabase.table("funil_negocios").delete().neq("id", SENTINEL_ID).execute()
        return before

    def sincronizar(self) -> dict:
        self._ensure_stages()
        removed = self._clear_negocios()

        pedidos_resp = listar_pedidos(page=1, page_size=500)
        pedidos = pedidos_resp.get("data") or []

        deals_created = 0
        total_value = 0.0
        customers_with_open_order: set[str] = set()

        for pedido in pedidos:
            status = pedido.get("status") or "pending"
            if status == "cancelled":
                continue

            stage_id = ORDER_STAGE_BY_STATUS.get(status)
            if not stage_id:
                continue

            customer_id = str(pedido.get("customerId") or "")
            if status in ("pending", "processing", "shipped"):
                customers_with_open_order.add(customer_id)

            valor = float(pedido.get("total") or 0)
            numero = pedido.get("number") or pedido.get("id")
            cliente = pedido.get("customerName") or "Cliente"

            self.repo.create_negocio({
                "id": f"deal-ped-{pedido.get('id')}",
                "stage_id": stage_id,
                "title": f"Pedido #{numero}",
                "contact": cliente,
                "value": round(valor, 2),
                "channel": "whatsapp",
            })
            deals_created += 1
            total_value += valor

        conversas = []
        try:
            conversas = self.conversas.listar()
        except Exception as exc:
            logger.warning("Conversas indisponíveis no sync do funil: %s", exc)

        for conv in conversas:
            if (conv.get("status") or "").lower() == "closed":
                continue

            cliente_id = str(conv.get("cliente_mercos_id") or "")
            if cliente_id and cliente_id in customers_with_open_order:
                continue

            conv_id = str(conv.get("id"))
            nome = conv.get("customer_name") or "Cliente"
            canal = conv.get("channel") or "whatsapp"
            ultima = (conv.get("last_message") or "")[:60]

            self.repo.create_negocio({
                "id": f"deal-conv-{conv_id}",
                "stage_id": "s1",
                "title": ultima or f"Conversa — {nome}",
                "contact": nome,
                "value": 0.0,
                "channel": canal,
            })
            deals_created += 1

        return {
            "success": True,
            "removed": removed,
            "dealsCreated": deals_created,
            "pipelineValor": round(total_value, 2),
            "pedidos": len(pedidos),
            "message": (
                f"Funil sincronizado: {deals_created} oportunidades "
                f"({removed} mock removidos). Pipeline pedidos: R$ {total_value:,.2f}."
            ).replace(",", "X").replace(".", ",").replace("X", "."),
        }


funil_sync_service = FunilSyncService()
