from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import verificar_token
from app.core.permissions import requer_permissao
from app.services.platform_service import platform_service

router = APIRouter()


class ChannelCreate(BaseModel):
    type: str
    name: str


class ChannelPatch(BaseModel):
    name: str | None = None
    phone: str | None = None
    connected: bool | None = None


class MoveDealRequest(BaseModel):
    dealId: str
    stageId: str


class CampaignCreate(BaseModel):
    name: str
    channel: str
    status: str
    recipients: int
    message: str | None = None
    scheduledAt: str | None = None


class ChatbotCreate(BaseModel):
    name: str
    channel: str
    active: bool = True


class ChatbotPatch(BaseModel):
    name: str | None = None
    active: bool | None = None


class ChatbotTestRequest(BaseModel):
    conversationId: str | None = None
    message: str | None = None


@router.get("/canais")
def get_canais(autorizado=Depends(verificar_token)):
    return platform_service.get_channels()


@router.post("/canais")
def connect_canal(body: ChannelCreate, _: dict = Depends(requer_permissao("managePlatform"))):
    return platform_service.connect_channel(body.type, body.name)


@router.patch("/canais/{channel_id}")
def update_canal(channel_id: str, body: ChannelPatch, _: dict = Depends(requer_permissao("managePlatform"))):
    channel = platform_service.update_channel(channel_id, body.model_dump(exclude_none=True))
    if not channel:
        raise HTTPException(status_code=404, detail="Canal não encontrado")
    return channel


@router.post("/canais/{channel_id}/toggle")
def toggle_canal(channel_id: str, _: dict = Depends(requer_permissao("managePlatform"))):
    channel = platform_service.toggle_channel(channel_id)
    if not channel:
        raise HTTPException(status_code=404, detail="Canal não encontrado")
    return channel


@router.get("/funil")
def get_funil(autorizado=Depends(verificar_token)):
    return platform_service.get_funnel()


@router.post("/funil/mover")
def mover_funil(body: MoveDealRequest, _: dict = Depends(requer_permissao("managePlatform"))):
    if not platform_service.move_deal(body.dealId, body.stageId):
        raise HTTPException(status_code=404, detail="Negócio não encontrado")
    return {"success": True}


@router.post("/funil/sincronizar")
def sincronizar_funil(_: dict = Depends(requer_permissao("managePlatform"))):
    from app.services.funil_sync_service import funil_sync_service

    return funil_sync_service.sincronizar()


@router.get("/campanhas")
def get_campanhas(autorizado=Depends(verificar_token)):
    return platform_service.get_campaigns()


@router.post("/campanhas")
def create_campanha(body: CampaignCreate, _: dict = Depends(requer_permissao("managePlatform"))):
    return platform_service.add_campaign(body.model_dump())


@router.post("/campanhas/{campaign_id}/disparar")
def disparar_campanha(campaign_id: str, _: dict = Depends(requer_permissao("managePlatform"))):
    return platform_service.dispatch_campaign(campaign_id)


@router.get("/chatbot/fluxos")
def get_chatbots(autorizado=Depends(verificar_token)):
    return platform_service.get_chatbots()


@router.post("/chatbot/fluxos")
def create_chatbot(body: ChatbotCreate, _: dict = Depends(requer_permissao("managePlatform"))):
    return platform_service.add_chatbot(body.model_dump())


@router.post("/chatbot/fluxos/{flow_id}/toggle")
def toggle_chatbot(flow_id: str, _: dict = Depends(requer_permissao("managePlatform"))):
    flow = platform_service.toggle_chatbot(flow_id)
    if not flow:
        raise HTTPException(status_code=404, detail="Fluxo não encontrado")
    return flow


@router.patch("/chatbot/fluxos/{flow_id}")
def update_chatbot(flow_id: str, body: ChatbotPatch, _: dict = Depends(requer_permissao("managePlatform"))):
    flow = platform_service.update_chatbot(flow_id, body.model_dump(exclude_none=True))
    if not flow:
        raise HTTPException(status_code=404, detail="Fluxo não encontrado")
    return flow


@router.post("/chatbot/fluxos/{flow_id}/testar")
def testar_chatbot(
    flow_id: str,
    body: ChatbotTestRequest | None = None,
    autorizado=Depends(verificar_token),
):
    from app.services.chatbot_service import chatbot_service

    try:
        return chatbot_service.test_flow(
            flow_id,
            conversation_id=body.conversationId if body else None,
            message=body.message if body else None,
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Teste do robô falhou: {exc}") from exc


@router.get("/integracoes")
def get_integracoes(autorizado=Depends(verificar_token)):
    return platform_service.get_integrations()


@router.post("/integracoes/{integration_id}/toggle")
def toggle_integracao(integration_id: str, _: dict = Depends(requer_permissao("manageIntegrations"))):
    item = platform_service.toggle_integration(integration_id)
    if not item:
        raise HTTPException(status_code=404, detail="Integração não encontrada")
    return item
