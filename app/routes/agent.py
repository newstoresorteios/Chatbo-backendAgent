from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from app.core.auth import verificar_token
from app.services.agent_service import agent_service

router = APIRouter()


class AgentChatRequest(BaseModel):
    message: str
    conversationId: str | None = None
    customerId: str | None = None
    mode: str | None = "copilot"
    history: list[dict] | None = None


class AgentSuggestRequest(BaseModel):
    conversationId: str
    customerId: str | None = None


@router.get("/agent/status")
def agent_status(autorizado=Depends(verificar_token)):
    return agent_service.status()


@router.get("/agent/context")
def agent_context(
    conversationId: str | None = None,
    customerId: str | None = None,
    message: str | None = None,
    autorizado=Depends(verificar_token),
):
    ctx = agent_service.build_context(conversationId, customerId, user_message=message)
    return {
        "conversation": ctx.get("conversation"),
        "customer": ctx.get("customer"),
        "customerDetail": ctx.get("customerDetail"),
        "messages": ctx.get("messages"),
        "lastCustomerMessage": ctx.get("lastCustomerMessage"),
        "productsCatalog": ctx.get("productsCatalog"),
        "products": ctx.get("products"),
        "orders": ctx.get("orders"),
        "relatedOrders": ctx.get("relatedOrders"),
        "recentOrders": ctx.get("recentOrders"),
        "salesMetrics": ctx.get("salesMetrics"),
        "platformStats": ctx.get("platformStats"),
    }


@router.post("/agent/chat")
def agent_chat(body: AgentChatRequest, autorizado=Depends(verificar_token)):
    return agent_service.chat(
        message=body.message,
        conversation_id=body.conversationId,
        customer_id=body.customerId,
        mode=body.mode or "copilot",
        history=body.history,
    )


@router.post("/agent/suggest")
def agent_suggest(body: AgentSuggestRequest, autorizado=Depends(verificar_token)):
    return agent_service.suggest(body.conversationId, body.customerId)


@router.post("/agent/restart")
def agent_restart(autorizado=Depends(verificar_token)):
    return {
        "success": True,
        "restartedAt": datetime.utcnow().isoformat(),
    }
