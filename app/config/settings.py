import os
from dotenv import load_dotenv

load_dotenv()

MERCOS_APPLICATION_TOKEN = os.getenv("MERCOS_APPLICATION_TOKEN")
MERCOS_COMPANY_TOKEN = os.getenv("MERCOS_COMPANY_TOKEN")
MERCOS_BASE_URL = os.getenv("MERCOS_BASE_URL")
MERCOS_ENV = os.getenv("MERCOS_ENV", "").strip().lower()


def mercos_ambiente() -> str:
    """sandbox | production | unknown"""
    if MERCOS_ENV in ("sandbox", "production"):
        return MERCOS_ENV
    url = (MERCOS_BASE_URL or "").lower()
    if "sandbox" in url:
        return "sandbox"
    if "api.mercos.com" in url:
        return "production"
    return "unknown"


def mercos_base_url_host() -> str | None:
    if not MERCOS_BASE_URL:
        return None
    try:
        from urllib.parse import urlparse
        return urlparse(MERCOS_BASE_URL).netloc or None
    except Exception:
        return MERCOS_BASE_URL

SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_KEY = (
    os.getenv("SUPABASE_KEY")
    or os.getenv("SUPABASE_SERVICE_ROLE_KEY")
    or os.getenv("SUPABASE_PUBLISHABLE_KEY")
    or os.getenv("SUPABASE_ANON_KEY")
)

FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
AUTH_RESET_DEBUG = os.getenv("AUTH_RESET_DEBUG", "true").lower() == "true"
JWT_SECRET = os.getenv("JWT_SECRET", "xnamai_secret_key_dev_only")
JWT_ALGORITHM = "HS256"
JWT_ACCESS_MINUTES = int(os.getenv("JWT_ACCESS_MINUTES", "30"))
JWT_REFRESH_DAYS = int(os.getenv("JWT_REFRESH_DAYS", "7"))

_JWT_SECRETS_FRACOS = frozenset({
    "",
    "xnamai_secret_key_dev_only",
    "gere-uma-chave-longa-e-aleatoria-aqui",
    "change-me",
    "secret",
})


def validar_jwt_secret() -> None:
    """Falha na subida se produção estiver com JWT_SECRET fraco ou ausente."""
    em_producao = bool(
        os.getenv("RENDER")
        or os.getenv("ENVIRONMENT", "").strip().lower() in ("production", "prod")
    )
    if not em_producao:
        return
    segredo = (JWT_SECRET or "").strip()
    if segredo in _JWT_SECRETS_FRACOS or len(segredo) < 32:
        raise RuntimeError(
            "JWT_SECRET inseguro em produção. Defina uma chave aleatória com pelo menos 32 caracteres no Render.",
        )

SMTP_HOST = os.getenv("SMTP_HOST", "smtp.gmail.com")
SMTP_PORT = int(os.getenv("SMTP_PORT", "587"))
SMTP_USER = os.getenv("SMTP_USER", "")
SMTP_PASSWORD = os.getenv("SMTP_PASSWORD", "")
SMTP_FROM_EMAIL = os.getenv("SMTP_FROM_EMAIL", SMTP_USER)
SMTP_FROM_NAME = os.getenv("SMTP_FROM_NAME", "PulseDesk")

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
OPENAI_MODEL = os.getenv("OPENAI_MODEL", "gpt-4o")
# Com API key: usa GPT sempre (sem fallback por regex). Desative só para dev local.
COPILOT_GPT_ONLY = os.getenv("COPILOT_GPT_ONLY", "true").lower() == "true"

# WhatsApp Meta Cloud API (Etapa 5)
META_APP_ID = os.getenv("META_APP_ID", "")
META_APP_SECRET = os.getenv("META_APP_SECRET", "")
META_ACCESS_TOKEN = os.getenv("META_ACCESS_TOKEN", "")
META_PHONE_NUMBER_ID = os.getenv("META_PHONE_NUMBER_ID", "")
META_WEBHOOK_VERIFY_TOKEN = os.getenv("META_WEBHOOK_VERIFY_TOKEN", "pulsedesk_whatsapp_verify")
META_API_VERSION = os.getenv("META_API_VERSION", "v21.0")
PUBLIC_API_URL = os.getenv("PUBLIC_API_URL", "http://localhost:8000")
NITRUS_INTERNAL_API_TOKEN = os.getenv("NITRUS_INTERNAL_API_TOKEN")

# ETL agendado (Render Cron) — sync Mercos → Supabase sem sobrecarregar a API
ETL_CRON_SECRET = os.getenv("ETL_CRON_SECRET", "")


def cors_origins() -> list[str]:
    origins = [
        "http://localhost:5173",
        "http://127.0.0.1:5173",
        "http://localhost:4173",
    ]
    if FRONTEND_URL:
        origins.append(FRONTEND_URL.rstrip("/"))
    extra = os.getenv("CORS_ORIGINS", "")
    for origin in extra.split(","):
        origin = origin.strip()
        if origin:
            origins.append(origin.rstrip("/"))
    return list(dict.fromkeys(origins))
