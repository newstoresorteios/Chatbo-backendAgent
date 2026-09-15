"""Private storage and validated metadata for WhatsApp conversation media."""

from __future__ import annotations

import re
import uuid

from fastapi import HTTPException

from app.services.supabase_service import supabase

BUCKET = "conversation-media"
MAX_BYTES = 16 * 1024 * 1024
ALLOWED_TYPES = {
    "image/jpeg": "image", "image/png": "image", "image/webp": "image",
    "audio/aac": "audio", "audio/mp4": "audio", "audio/mpeg": "audio",
    "audio/ogg": "audio", "audio/amr": "audio",
    "application/pdf": "document", "text/plain": "document",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document": "document",
}


def safe_filename(name: str) -> str:
    base = (name or "arquivo").replace("\\", "/").split("/")[-1]
    return re.sub(r"[^a-zA-Z0-9._-]", "_", base).strip("._")[:120] or "arquivo"


def validate_media(content: bytes, content_type: str) -> str:
    kind = ALLOWED_TYPES.get(content_type)
    if not kind:
        raise HTTPException(400, "Formato não suportado. Use imagem, áudio, PDF, TXT ou DOCX.")
    if not content or len(content) > MAX_BYTES:
        raise HTTPException(400, "Arquivo vazio ou maior que 16 MB.")
    return kind


def store_media(workspace_id: str, conversation_id: str, filename: str,
                content: bytes, content_type: str) -> str:
    path = f"{workspace_id}/{conversation_id}/{uuid.uuid4().hex}-{safe_filename(filename)}"
    supabase.storage.from_(BUCKET).upload(
        path, content, {"content-type": content_type, "upsert": "false"}
    )
    return path


def signed_media_url(path: str | None) -> str | None:
    if not path:
        return None
    result = supabase.storage.from_(BUCKET).create_signed_url(path, 900)
    return result.get("signedURL") or result.get("signedUrl")
