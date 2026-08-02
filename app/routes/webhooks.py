import json

from fastapi import APIRouter, HTTPException, Query, Request, Response

from app.config.settings import META_WEBHOOK_VERIFY_TOKEN
from app.providers.whatsapp_meta import WhatsAppMetaProvider
from app.services.whatsapp_service import whatsapp_service

router = APIRouter()


@router.get("/webhooks/whatsapp")
def verificar_webhook_whatsapp(
    hub_mode: str | None = Query(None, alias="hub.mode"),
    hub_verify_token: str | None = Query(None, alias="hub.verify_token"),
    hub_challenge: str | None = Query(None, alias="hub.challenge"),
):
    if not hub_mode and not hub_verify_token and not hub_challenge:
        return {
            "status": "ok",
            "message": (
                "Endpoint do webhook WhatsApp ativo. "
                "Abrir no navegador não configura a Meta — use o painel Meta Developer."
            ),
            "verifyToken": META_WEBHOOK_VERIFY_TOKEN or "pulsedesk_whatsapp_verify",
            "fields": ["messages"],
        }

    try:
        challenge = whatsapp_service.verificar_webhook(hub_mode, hub_verify_token, hub_challenge)
    except HTTPException as exc:
        if exc.status_code == 403:
            raise HTTPException(
                status_code=403,
                detail=(
                    "Verificação do webhook falhou. "
                    f"Confira se o Verify Token na Meta é exatamente: {META_WEBHOOK_VERIFY_TOKEN or 'pulsedesk_whatsapp_verify'}"
                ),
            ) from exc
        raise

    return Response(content=challenge, media_type="text/plain")

@router.post("/webhooks/whatsapp")
async def receber_webhook_whatsapp(request: Request):
    body = await request.body()
    signature = request.headers.get("X-Hub-Signature-256")

    provider = WhatsAppMetaProvider()
    if not provider.verificar_assinatura(body, signature):
        return {"success": False, "detail": "Assinatura inválida"}

    payload = json.loads(body)
    result = whatsapp_service.processar_webhook(payload)
    return {"success": True, **result}
