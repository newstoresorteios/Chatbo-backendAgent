import secrets

from fastapi import Header, HTTPException

from app.config.settings import NITRUS_INTERNAL_API_TOKEN


def require_nitrus_internal_token(
    token: str | None = Header(default=None, alias="X-NITRUS-Internal-Token"),
) -> None:
    """Authorizes only the dedicated service token, never a user JWT."""
    if not NITRUS_INTERNAL_API_TOKEN or not token:
        raise HTTPException(status_code=401, detail="Credencial interna inválida.")
    if not secrets.compare_digest(token, NITRUS_INTERNAL_API_TOKEN):
        raise HTTPException(status_code=401, detail="Credencial interna inválida.")
