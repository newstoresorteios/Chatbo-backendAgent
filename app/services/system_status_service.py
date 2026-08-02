import logging

from app.services.agent_service import agent_service
from app.services.pulsedesk_adapter import mercos_status
from app.services.supabase_service import supabase
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)


def _normalizar_telefone(valor: str | None) -> str | None:
    if not valor:
        return None
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    if len(digitos) < 10:
        return None
    return digitos


def _check_supabase() -> dict:
    try:
        resposta = (
            supabase
            .table("usuarios")
            .select("id", count="exact")
            .limit(1)
            .execute()
        )
        total = getattr(resposta, "count", None)
        if total is None and resposta.data is not None:
            total = len(resposta.data)
        return {
            "ok": True,
            "message": "Banco de dados acessível",
            "users": int(total or 0),
        }
    except Exception as exc:
        logger.warning("Falha ao verificar Supabase: %s", exc)
        return {
            "ok": False,
            "message": "Não foi possível acessar o Supabase",
            "error": str(exc)[:120],
        }


def _count_customers_with_phone() -> int:
    try:
        rows = (
            supabase
            .table("clientes")
            .select("telefone,celular")
            .execute()
            .data
            or []
        )
    except Exception as exc:
        logger.warning("Falha ao contar clientes com telefone: %s", exc)
        return 0

    vistos: set[str] = set()
    for row in rows:
        phone = _normalizar_telefone(row.get("celular") or row.get("telefone"))
        if phone:
            vistos.add(phone)
    return len(vistos)


class SystemStatusService:

    def __init__(self):
        self.whatsapp = WhatsAppService()

    def get_status(self) -> dict:
        supabase_status = _check_supabase()
        mercos = mercos_status()
        whatsapp = self.whatsapp.status()
        agent = agent_service.status()
        customers_with_phone = _count_customers_with_phone()

        mercos_configured = bool(mercos.get("connected"))
        mercos_synced = int(mercos.get("syncedCustomers") or 0) > 0
        whatsapp_ready = bool(whatsapp.get("connected"))
        openai_ready = bool(agent.get("openaiEnabled"))

        checklist = [
            {
                "id": "supabase",
                "title": "Banco de dados (Supabase)",
                "description": "Login e persistência de dados",
                "done": bool(supabase_status.get("ok")),
                "settingsTab": "sistema",
            },
            {
                "id": "mercos_tokens",
                "title": "Tokens Mercos no Render",
                "description": "MERCOS_APPLICATION_TOKEN e MERCOS_COMPANY_TOKEN",
                "done": mercos_configured,
                "settingsTab": "mercos",
            },
            {
                "id": "mercos_sync",
                "title": "Sincronizar clientes e pedidos",
                "description": "Importar dados comerciais do Mercos",
                "done": mercos_synced,
                "settingsTab": "mercos",
            },
            {
                "id": "mercos_products",
                "title": "Sincronizar produtos",
                "description": "Catálogo no PulseDesk e no agente (Supabase)",
                "done": int(mercos.get("syncedProducts") or 0) > 0,
                "settingsTab": "mercos",
            },
            {
                "id": "whatsapp",
                "title": "WhatsApp Meta (opcional)",
                "description": "Demo de vendas usa Z-API no agent-ia-xnamai; Meta é só se for API oficial",
                "done": whatsapp_ready,
                "settingsTab": "whatsapp",
                "optional": True,
            },
            {
                "id": "openai",
                "title": "Ativar IA (OpenAI)",
                "description": "OPENAI_API_KEY no Render — robô e copiloto",
                "done": openai_ready,
                "settingsTab": "openai",
            },
            {
                "id": "campaign_recipients",
                "title": "Clientes com telefone",
                "description": "Necessário para campanhas WhatsApp",
                "done": customers_with_phone > 0,
                "settingsTab": "mercos",
            },
        ]
        # Prontidão: ignora itens opcionais (Meta WA / nota do agente Z-API)
        checklist_obrigatorio = [item for item in checklist if not item.get("optional")]
        done_count = sum(1 for item in checklist_obrigatorio if item["done"])
        total = len(checklist_obrigatorio)

        return {
            "supabase": supabase_status,
            "mercos": {
                "configured": mercos_configured,
                "environment": mercos.get("environment"),
                "isProduction": bool(mercos.get("isProduction")),
                "baseUrlHost": mercos.get("baseUrlHost"),
                "lastSync": mercos.get("lastSync"),
                "syncedProducts": int(mercos.get("syncedProducts") or 0),
                "syncedCustomers": int(mercos.get("syncedCustomers") or 0),
                "syncedOrders": int(mercos.get("syncedOrders") or 0),
            },
            "whatsapp": {
                "configured": bool(whatsapp.get("configured")),
                "connected": whatsapp_ready,
                "provider": whatsapp.get("provider"),
                "webhookUrl": whatsapp.get("webhookUrl"),
                "displayPhone": whatsapp.get("displayPhone"),
                "message": whatsapp.get("message"),
            },
            "openai": {
                "configured": openai_ready,
                "mode": agent.get("intelligenceMode") or "local",
                "model": agent.get("model"),
                "gptOnly": bool(agent.get("gptOnly")),
            },
            "data": {
                "customersWithPhone": customers_with_phone,
            },
            "readiness": {
                "completed": done_count,
                "total": total,
                "percent": round((done_count / total) * 100) if total else 0,
            },
            "checklist": checklist,
        }


system_status_service = SystemStatusService()
