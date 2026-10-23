"""Authenticated YCloud channel controls and public signed webhook."""

import json
import os

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from app.core.permissions import requer_permissao
from app.core.workspace_scope import obter_company_context, workspace_id_from_context
from app.providers.whatsapp_ycloud import verify_signature
from app.services.ycloud_service import ycloud_service

api_router = APIRouter()
webhook_router = APIRouter()


class ConnectRequest(BaseModel):
    name: str = Field(min_length=2, max_length=100)


@api_router.get("/ycloud/status")
def ycloud_status(context: dict = Depends(obter_company_context)):
    return ycloud_service.status(workspace_id_from_context(context))


@api_router.post("/ycloud/conectar")
def connect_ycloud(body: ConnectRequest, _admin: dict = Depends(requer_permissao("managePlatform")),
                   context: dict = Depends(obter_company_context)):
    try:
        return ycloud_service.connect(workspace_id_from_context(context), body.name)
    except ValueError as exc:
        raise HTTPException(400, str(exc)) from exc
    except Exception as exc:
        if isinstance(exc, HTTPException):
            raise
        raise HTTPException(502, "Não foi possível validar o número na YCloud") from exc


@webhook_router.post("/webhooks/ycloud")
async def receive_ycloud_webhook(request: Request, background_tasks: BackgroundTasks):
    secret = os.getenv("YCLOUD_WEBHOOK_SECRET", "").strip()
    if not secret:
        raise HTTPException(503, "Webhook YCloud não configurado")
    body = await request.body()
    if not verify_signature(body, request.headers.get("YCloud-Signature"), secret):
        raise HTTPException(401, "Assinatura YCloud inválida")
    try:
        event = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        raise HTTPException(400, "JSON YCloud inválido") from exc
    if not isinstance(event, dict):
        raise HTTPException(400, "Evento YCloud inválido")
    result = ycloud_service.process_event(event)
    for job in result.get("bot_jobs") or []:
        background_tasks.add_task(ycloud_service.reply_if_eligible, *job)
    return {"processed": result.get("processed", 0)}
