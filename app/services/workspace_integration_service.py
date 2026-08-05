"""Integrações de workspace (Mercos / TRAYadaptor)."""

from __future__ import annotations

from datetime import datetime

from fastapi import HTTPException

from app.services.supabase_service import supabase
from app.services.tray_adaptor_client import TrayAdaptorClient


class WorkspaceIntegrationService:
    def get(self, workspace_id: str, provider: str = "tray") -> dict | None:
        resposta = (
            supabase.table("workspace_integrations")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("provider", provider)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def upsert_tray(
        self,
        workspace_id: str,
        *,
        adapter_base_url: str,
        adapter_token: str | None = None,
        enabled: bool = True,
    ) -> dict:
        base = (adapter_base_url or "").strip().rstrip("/")
        token = (adapter_token or "").strip()
        if not base.startswith("http"):
            raise HTTPException(status_code=400, detail="Informe a URL completa do TRAYadaptor.")

        existing = self.get(workspace_id, "tray")
        existing_config = (existing or {}).get("configuration") or {}
        if not isinstance(existing_config, dict):
            existing_config = {}
        if not token:
            token = str(existing_config.get("adapterToken") or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail="Informe o token interno do TRAYadaptor.")

        status = "connected" if enabled else "disconnected"
        configuration = {
            "adapterBaseUrl": base,
            "adapterToken": token,
        }
        payload = {
            "workspace_id": workspace_id,
            "provider": "tray",
            "status": status,
            "configuration": configuration,
            "last_error": None,
            "updated_at": datetime.utcnow().isoformat(),
        }
        if existing:
            resposta = (
                supabase.table("workspace_integrations")
                .update(payload)
                .eq("id", existing["id"])
                .execute()
            )
            rows = resposta.data or []
            return rows[0] if rows else {**existing, **payload}
        resposta = supabase.table("workspace_integrations").insert(payload).execute()
        rows = resposta.data or []
        return rows[0] if rows else payload

    def public_view(self, row: dict | None) -> dict:
        if not row:
            return {
                "provider": "tray",
                "enabled": False,
                "adapterBaseUrl": "",
                "hasToken": False,
                "status": "disconnected",
                "lastSyncAt": None,
                "lastError": None,
            }
        config = row.get("configuration") or {}
        if not isinstance(config, dict):
            config = {}
        token = str(config.get("adapterToken") or "")
        return {
            "provider": "tray",
            "enabled": row.get("status") == "connected",
            "adapterBaseUrl": config.get("adapterBaseUrl") or "",
            "hasToken": bool(token),
            "status": row.get("status") or "disconnected",
            "lastSyncAt": row.get("last_sync_at"),
            "lastError": row.get("last_error"),
        }

    def client_from_workspace(self, workspace_id: str) -> TrayAdaptorClient:
        row = self.get(workspace_id, "tray")
        if not row or row.get("status") != "connected":
            raise HTTPException(
                status_code=400,
                detail="TRAYadaptor não configurado para esta empresa. Aponte a URL no superadmin.",
            )
        config = row.get("configuration") or {}
        base = str(config.get("adapterBaseUrl") or "").strip()
        token = str(config.get("adapterToken") or "").strip()
        if not base or not token:
            raise HTTPException(status_code=400, detail="Configuração do TRAYadaptor incompleta.")
        return TrayAdaptorClient(base, token)

    def test_connection(self, workspace_id: str | None = None, *, base_url: str | None = None, token: str | None = None) -> dict:
        if workspace_id and not (base_url and token):
            client = self.client_from_workspace(workspace_id)
        else:
            if not base_url or not token:
                raise HTTPException(status_code=400, detail="Informe adapterBaseUrl e adapterToken.")
            client = TrayAdaptorClient(base_url, token)
        health = client.health()
        products = client.list_products(page=1, limit=1)
        return {
            "ok": True,
            "health": health,
            "sampleProducts": len(products),
        }


workspace_integration_service = WorkspaceIntegrationService()
