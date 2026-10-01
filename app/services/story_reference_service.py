from __future__ import annotations

import re
import unicodedata
from datetime import datetime, timezone
from urllib.parse import urlsplit, urlunsplit

from fastapi import HTTPException

from app.config.settings import NSAGENT_PERSONA_TENANT_ID
from app.services.supabase_service import supabase
from app.services.workspace_service import WORKSPACE_ADMIN_ROLES, workspace_service


ALLOWED_STORE_HOSTS = {
    "newstorerj.com", "www.newstorerj.com",
    "newstorerj.com.br", "www.newstorerj.com.br",
}


def _normalize_name(value: str) -> str:
    folded = unicodedata.normalize("NFKD", value.strip().casefold())
    ascii_text = "".join(ch for ch in folded if not unicodedata.combining(ch))
    return re.sub(r"[^a-z0-9]+", " ", ascii_text).strip()


def _normalize_product_url(value: str) -> str:
    try:
        parsed = urlsplit(value.strip())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="Link do produto inválido") from exc
    host = (parsed.hostname or "").casefold()
    if parsed.scheme.casefold() != "https" or host not in ALLOWED_STORE_HOSTS:
        raise HTTPException(status_code=422, detail="Use um link HTTPS oficial da New Store")
    if not parsed.path or parsed.path == "/":
        raise HTTPException(status_code=422, detail="Informe o link completo do produto")
    normalized_host = "www.newstorerj.com.br" if host.endswith(".com.br") else "www.newstorerj.com"
    return urlunsplit(("https", normalized_host, parsed.path.rstrip("/"), parsed.query, ""))


def _public(row: dict) -> dict:
    return {
        "id": int(row["id"]), "workspaceId": row.get("workspace_id"),
        "tenantId": row.get("tenant_id"), "name": row.get("name"),
        "url": row.get("product_url"), "active": bool(row.get("active", True)),
        "createdBy": row.get("created_by"), "updatedBy": row.get("updated_by"),
        "createdAt": row.get("created_at"), "updatedAt": row.get("updated_at"),
    }


class StoryReferenceService:
    def tenant_id(self) -> str:
        return (NSAGENT_PERSONA_TENANT_ID or "newstore").strip()

    def _scope(self, usuario: dict) -> tuple[str, str, str]:
        context = workspace_service.get_current_workspace_context(usuario)
        return str(context["workspaceId"]), self.tenant_id(), str(context.get("workspaceRole") or "")

    @staticmethod
    def _require_admin(role: str) -> None:
        if role not in WORKSPACE_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Apenas proprietários e administradores podem alterar referências")

    def list(self, usuario: dict, *, include_inactive: bool = True) -> dict:
        workspace_id, tenant_id, _ = self._scope(usuario)
        query = (supabase.table("ai_story_highlight_references").select("*")
                 .eq("workspace_id", workspace_id).eq("tenant_id", tenant_id).order("name"))
        if not include_inactive:
            query = query.eq("active", True)
        rows = query.execute().data or []
        return {"items": [_public(row) for row in rows], "total": len(rows)}

    def create(self, usuario: dict, *, name: str, url: str) -> dict:
        workspace_id, tenant_id, role = self._scope(usuario)
        self._require_admin(role)
        clean_name = " ".join(name.split()).strip()
        normalized_name = _normalize_name(clean_name)
        if len(clean_name) < 2 or not normalized_name:
            raise HTTPException(status_code=422, detail="Informe o nome do relógio")
        product_url = _normalize_product_url(url)
        now = datetime.now(timezone.utc).isoformat()
        actor = str(usuario.get("id") or "") or None
        try:
            result = supabase.table("ai_story_highlight_references").insert({
                "workspace_id": workspace_id, "tenant_id": tenant_id,
                "name": clean_name[:200], "normalized_name": normalized_name[:200],
                "product_url": product_url, "active": True,
                "created_by": actor, "updated_by": actor,
                "created_at": now, "updated_at": now,
            }).execute()
        except Exception as exc:
            if "duplicate" in str(exc).casefold() or "23505" in str(exc):
                raise HTTPException(status_code=409, detail="Este relógio ou link já está cadastrado") from exc
            raise
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=502, detail="Não foi possível cadastrar a referência")
        return _public(rows[0])

    def update(self, usuario: dict, reference_id: int, changes: dict) -> dict:
        workspace_id, tenant_id, role = self._scope(usuario)
        self._require_admin(role)
        payload: dict = {"updated_at": datetime.now(timezone.utc).isoformat(), "updated_by": str(usuario.get("id") or "") or None}
        if "name" in changes:
            clean_name = " ".join(str(changes["name"] or "").split()).strip()
            normalized_name = _normalize_name(clean_name)
            if len(clean_name) < 2 or not normalized_name:
                raise HTTPException(status_code=422, detail="Informe o nome do relógio")
            payload.update(name=clean_name[:200], normalized_name=normalized_name[:200])
        if "url" in changes:
            payload["product_url"] = _normalize_product_url(str(changes["url"] or ""))
        if "active" in changes:
            payload["active"] = bool(changes["active"])
        try:
            result = (supabase.table("ai_story_highlight_references").update(payload)
                      .eq("id", reference_id).eq("workspace_id", workspace_id)
                      .eq("tenant_id", tenant_id).execute())
        except Exception as exc:
            if "duplicate" in str(exc).casefold() or "23505" in str(exc):
                raise HTTPException(status_code=409, detail="Este relógio ou link já está cadastrado") from exc
            raise
        rows = result.data or []
        if not rows:
            raise HTTPException(status_code=404, detail="Referência não encontrada")
        return _public(rows[0])

    def delete(self, usuario: dict, reference_id: int) -> None:
        workspace_id, tenant_id, role = self._scope(usuario)
        self._require_admin(role)
        result = (supabase.table("ai_story_highlight_references").delete()
                  .eq("id", reference_id).eq("workspace_id", workspace_id)
                  .eq("tenant_id", tenant_id).execute())
        if not (result.data or []):
            raise HTTPException(status_code=404, detail="Referência não encontrada")


story_reference_service = StoryReferenceService()
