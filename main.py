import os
import sys

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
from app.routes.agents import router as agents_router

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
api.include_router(agents_router, tags=["Agents"])
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
    import re
    from urllib.parse import urlparse

    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    if not os.getenv("JWT_SECRET"):
        missing.append("JWT_SECRET")

    supabase_host = None
    supabase_url_ok = False
    supabase_url_preview = None
    if SUPABASE_URL:
        cleaned = SUPABASE_URL.strip().rstrip("/")
        supabase_url_ok = bool(re.match(r"^(https?)://.+", cleaned))
        supabase_url_preview = repr(cleaned[:48])
        try:
            supabase_host = urlparse(cleaned).hostname
        except Exception:
            supabase_host = None

    payload = {
        "supabase_url_ok": supabase_url_ok,
        "supabase_host": supabase_host,
        "supabase_url_preview": supabase_url_preview,
        "supabase_key_set": bool(SUPABASE_KEY),
        "python": sys.version.split()[0],
    }
    if missing:
        return {"status": "degraded", "missing_env": missing, **payload}
    return {"status": "ok" if supabase_url_ok else "degraded", **payload}


@app.get("/health/db")
def health_db():
    """Diagnostico leve da conexao Supabase (sem dados sensiveis)."""
    missing = []
    if not SUPABASE_URL:
        missing.append("SUPABASE_URL")
    if not SUPABASE_KEY:
        missing.append("SUPABASE_KEY")
    if missing:
        return {"status": "degraded", "missing_env": missing, "db": "skipped"}

    try:
        from app.services.supabase_service import get_supabase

        client = get_supabase()
        resposta = client.table("usuarios").select("id").limit(1).execute()
        return {
            "status": "ok",
            "db": "ok",
            "usuarios_sample": len(resposta.data or []),
        }
    except Exception as exc:
        return {
            "status": "error",
            "db": "error",
            "error_type": type(exc).__name__,
            "error": str(exc)[:500],
        }
