from fastapi import APIRouter

from app.routes.ai.commerce import router as commerce_router
from app.routes.ai.memory import router as memory_router
from app.routes.ai.messages import router as messages_router
from app.routes.ai.persona_runtime import router as persona_runtime_router
from app.routes.ai.remarketing import router as remarketing_router

router = APIRouter()
router.include_router(messages_router)
router.include_router(remarketing_router)
router.include_router(memory_router)
router.include_router(commerce_router)
router.include_router(persona_runtime_router)
