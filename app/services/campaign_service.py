import logging
import re
import time
from datetime import datetime

from fastapi import HTTPException

from app.repositories.cliente_repository import ClienteRepository
from app.repositories.platform_repository import PlatformRepository
from app.services.supabase_service import supabase
from app.services.whatsapp_service import WhatsAppService

logger = logging.getLogger(__name__)

_TEMPLATE_NOME = re.compile(r"\{\{\s*nome\s*\}\}", re.IGNORECASE)


def _normalizar_telefone(valor: str | None) -> str | None:
    if not valor:
        return None
    digitos = "".join(ch for ch in str(valor) if ch.isdigit())
    if len(digitos) < 10:
        return None
    if len(digitos) in (10, 11) and not digitos.startswith("55"):
        digitos = f"55{digitos}"
    return digitos


def _nome_cliente(cliente: dict) -> str:
    return (cliente.get("nome") or cliente.get("razao_social") or "Cliente").strip()


def _aplicar_template(mensagem: str, nome: str) -> str:
    return _TEMPLATE_NOME.sub(nome, mensagem)


class CampaignService:

    def __init__(self):
        self.campanhas = PlatformRepository()
        self.clientes = ClienteRepository()
        self.whatsapp = WhatsAppService()

    def _destinatarios(self, limite: int) -> list[dict]:
        vistos: set[str] = set()
        destinatarios: list[dict] = []

        try:
            rows = self.clientes.listar_com_telefone(limite if limite > 0 else None)
        except Exception as exc:
            logger.warning("Falha ao listar clientes para campanha: %s", exc)
            rows = []

        for row in rows:
            phone = _normalizar_telefone(row.get("celular") or row.get("telefone"))
            if not phone or phone in vistos:
                continue
            vistos.add(phone)
            destinatarios.append({
                "phone": phone,
                "name": _nome_cliente(row),
            })
            if limite > 0 and len(destinatarios) >= limite:
                return destinatarios

        if destinatarios:
            return destinatarios

        try:
            conversas = (
                supabase
                .table("conversas")
                .select("contact_phone,external_thread_id,customer_name")
                .eq("channel", "whatsapp")
                .execute()
                .data
                or []
            )
        except Exception as exc:
            logger.warning("Falha ao listar conversas para campanha: %s", exc)
            return []

        for conversa in conversas:
            phone = _normalizar_telefone(
                conversa.get("contact_phone") or conversa.get("external_thread_id")
            )
            if not phone or phone in vistos:
                continue
            vistos.add(phone)
            destinatarios.append({
                "phone": phone,
                "name": (conversa.get("customer_name") or "Cliente").strip(),
            })
            if limite > 0 and len(destinatarios) >= limite:
                break

        return destinatarios

    def disparar(self, campanha_id: str) -> dict:
        campanha = self.campanhas.get_campanha(campanha_id)
        if not campanha:
            raise HTTPException(status_code=404, detail="Campanha não encontrada")

        if campanha.get("channel") != "whatsapp":
            raise HTTPException(
                status_code=400,
                detail="Disparo disponível apenas para campanhas WhatsApp.",
            )

        status = campanha.get("status")
        if status not in ("draft", "scheduled"):
            raise HTTPException(
                status_code=400,
                detail=f"Campanha com status '{status}' não pode ser disparada.",
            )

        mensagem = (campanha.get("message") or "").strip()
        if not mensagem:
            raise HTTPException(
                status_code=400,
                detail="Defina a mensagem da campanha antes de disparar.",
            )

        canal = self.whatsapp._resolve_canal()
        provider = self.whatsapp._provider_for_canal(canal)
        if not provider.configurado() or not (canal or {}).get("connected", True):
            raise HTTPException(
                status_code=503,
                detail="WhatsApp não conectado. Configure o canal em Canais antes de disparar.",
            )

        limite = int(campanha.get("recipients") or 0)
        destinatarios = self._destinatarios(limite)
        if not destinatarios:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Nenhum destinatário com telefone encontrado. "
                    "Sincronize clientes do Mercos ou tenha conversas WhatsApp ativas."
                ),
            )

        self.campanhas.update_campanha(campanha_id, {
            "status": "running",
            "recipients": len(destinatarios),
            "sent": 0,
            "failed": 0,
            "opened": 0,
            "last_error": None,
        })

        enviados = 0
        falhas = 0
        ultimo_erro: str | None = None

        for dest in destinatarios:
            texto = _aplicar_template(mensagem, dest["name"])
            try:
                provider.enviar_texto(dest["phone"], texto)
                enviados += 1
            except Exception as exc:
                falhas += 1
                ultimo_erro = str(exc)
                logger.warning(
                    "Falha ao enviar campanha %s para %s: %s",
                    campanha_id,
                    dest["phone"][-4:],
                    exc,
                )
            time.sleep(0.15)

        status_final = "completed" if enviados > 0 else "draft"
        atualizado = self.campanhas.update_campanha(campanha_id, {
            "status": status_final,
            "sent": enviados,
            "failed": falhas,
            "opened": 0,
            "dispatched_at": datetime.utcnow().isoformat(),
            "last_error": ultimo_erro,
        }) or campanha

        if canal:
            self.campanhas.update_canal(canal["id"], {
                "last_activity": datetime.utcnow().isoformat(),
            })

        return {
            "success": enviados > 0,
            "campaignId": campanha_id,
            "recipients": len(destinatarios),
            "sent": enviados,
            "failed": falhas,
            "status": atualizado.get("status", status_final),
            "message": (
                f"Campanha enviada para {enviados} de {len(destinatarios)} destinatários."
                if enviados
                else "Nenhuma mensagem foi enviada. Verifique a conexão WhatsApp."
            ),
        }


campaign_service = CampaignService()
