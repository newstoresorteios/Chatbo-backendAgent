"""Upload/download de documentos de conhecimento da persona (Supabase Storage)."""

from __future__ import annotations

import logging
import re
import uuid

import httpx

from app.config.settings import (
    PERSONA_KNOWLEDGE_BUCKET,
    SUPABASE_KEY,
    SUPABASE_URL,
)

logger = logging.getLogger(__name__)

_SAFE_NAME = re.compile(r"[^a-zA-Z0-9._-]+")


def _safe_filename(name: str) -> str:
    base = (name or "arquivo").strip().replace("\\", "/").split("/")[-1]
    cleaned = _SAFE_NAME.sub("_", base).strip("._") or "arquivo"
    return cleaned[:180]


class PersonaStorageService:
    def __init__(self, bucket: str | None = None) -> None:
        self.bucket = (bucket or PERSONA_KNOWLEDGE_BUCKET or "persona-knowledge").strip()

    def _headers(self, content_type: str) -> dict[str, str]:
        if not SUPABASE_URL or not SUPABASE_KEY:
            raise RuntimeError("supabase_storage_not_configured")
        return {
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": content_type or "application/octet-stream",
            "x-upsert": "true",
        }

    def upload(
        self,
        *,
        workspace_id: str,
        persona_id: str,
        filename: str,
        content: bytes,
        content_type: str,
    ) -> str:
        safe = _safe_filename(filename)
        object_path = f"{workspace_id}/{persona_id}/{uuid.uuid4().hex}-{safe}"
        url = (
            f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/"
            f"{self.bucket}/{object_path}"
        )
        with httpx.Client(timeout=120.0) as client:
            response = client.post(url, content=content, headers=self._headers(content_type))
            if response.status_code >= 400:
                logger.error(
                    "persona storage upload failed status=%s body=%s",
                    response.status_code,
                    response.text[:500],
                )
                raise RuntimeError(f"supabase_upload_failed_{response.status_code}")
        return object_path

    def delete(self, storage_path: str) -> None:
        if not storage_path:
            return
        url = (
            f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/"
            f"{self.bucket}/{storage_path}"
        )
        with httpx.Client(timeout=60.0) as client:
            response = client.delete(
                url,
                headers={
                    "Authorization": f"Bearer {SUPABASE_KEY}",
                },
            )
            if response.status_code >= 400 and response.status_code != 404:
                logger.warning(
                    "persona storage delete failed status=%s path=%s",
                    response.status_code,
                    storage_path,
                )


persona_storage = PersonaStorageService()
