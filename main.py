import os

from fastapi import APIRouter, FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config.settings import SUPABASE_KEY, SUPABASE_URL, cors_origins, validar_jwt_secret
from app.routes.login import router as login_router
from app.routes.database import router as database_router
from app.routes.dashboard import router as dashboard_router
from app.routes.sincronizacao import router as sincronizacao_router
from app.routes.pulsedesk import router as pulsedesk_router
from app.routes.mercos import router as mercos_router
from app.routes.platform import router as platform_router
from app.routes.conversas import router as conversas_router
from app.routes.agent import router as agent_router
from app.routes.usuarios import router as usuarios_router
from app.routes.whatsapp import router as whatsapp_router
from app.routes.settings import router as settings_router
from app.routes.system import router as system_router
from app.routes.webhooks import router as webhooks_router
from app.routes.etl import router as etl_router
from app.routes.workspace import router as workspace_router
from app.routes.personas import router as personas_router
from app.routes.billing import router as billing_router
from app.routes.internal import router as internal_router

validar_jwt_secret()

app = FastAPI(
    title="PulseDesk Backend",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=cors_origins(),
    allow_origin_regex=r"https://([a-z0-9-]+\.)*vercel\.app",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

api = APIRouter(prefix="/api")

api.include_router(login_router, prefix="/auth", tags=["Auth"])
api.include_router(pulsedesk_router, tags=["PulseDesk"])
api.include_router(platform_router, tags=["Platform"])
api.include_router(conversas_router, tags=["Conversas"])
api.include_router(agent_router, tags=["Agent"])
api.include_router(usuarios_router, tags=["Usuarios"])
api.include_router(whatsapp_router, tags=["WhatsApp"])
api.include_router(settings_router, tags=["Settings"])
api.include_router(system_router, tags=["System"])
api.include_router(workspace_router, tags=["Workspace"])
api.include_router(personas_router, tags=["Personas"])
api.include_router(billing_router, tags=["Billing"])
api.include_router(internal_router, tags=["Internal"])
api.include_router(mercos_router, prefix="/mercos", tags=["Mercos"])
api.include_router(database_router, prefix="/database", tags=["Database"])
api.include_router(dashboard_router, prefix="/dashboard", tags=["Dashboard"])
api.include_router(sincronizacao_router, prefix="/sincronizacao", tags=["Sincronizacao"])
api.include_router(etl_router, tags=["ETL"])

app.include_router(api)
app.include_router(webhooks_router, tags=["Webhooks"])


@app.get("/")
def home():
    return {"status": "online"}


@app.get("/health")
def health():
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    if not os.getenv("JWT_SECRET"):
        missing.append("JWT_SECRET")
    if missing:
        return {"status": "degraded", "missing_env": missing}
    return {"status": "ok"}
