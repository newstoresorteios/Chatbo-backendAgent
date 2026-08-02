import secrets
import uuid
from datetime import datetime, timedelta

from jose import jwt

from app.config.settings import (
    JWT_ACCESS_MINUTES,
    JWT_ALGORITHM,
    JWT_REFRESH_DAYS,
    JWT_SECRET,
)


def criar_access_token(dados: dict) -> tuple[str, str, datetime]:
    jti = str(uuid.uuid4())
    expira = datetime.utcnow() + timedelta(minutes=JWT_ACCESS_MINUTES)
    payload = {
        **dados,
        "jti": jti,
        "type": "access",
        "exp": expira,
    }
    token = jwt.encode(payload, JWT_SECRET, algorithm=JWT_ALGORITHM)
    return token, jti, expira


def criar_refresh_token_opaco() -> tuple[str, datetime]:
    expira = datetime.utcnow() + timedelta(days=JWT_REFRESH_DAYS)
    return secrets.token_urlsafe(48), expira


def decodificar_token(token: str) -> dict:
    return jwt.decode(token, JWT_SECRET, algorithms=[JWT_ALGORITHM])
