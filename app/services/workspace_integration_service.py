"""Integrações de comércio por workspace (MercosAdaptor / TRAYadaptor)."""

from __future__ import annotations

from datetime import datetime, timezone

from fastapi import HTTPException

from app.services.supabase_service import supabase
from app.services.tray_adaptor_client import TrayAdaptorClient


class WorkspaceIntegrationService:
    SUPPORTED_PROVIDERS = frozenset({"mercos", "tray"})

    def _provider(self, provider: str | None) -> str:
        normalized = str(provider or "").strip().lower()
        if normalized not in self.SUPPORTED_PROVIDERS:
            raise HTTPException(status_code=400, detail="Provider deve ser mercos ou tray.")
        return normalized

    def get(self, workspace_id: str, provider: str = "tray") -> dict | None:
        provider = self._provider(provider)
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

    def get_configured(self, workspace_id: str) -> dict | None:
        """Retorna a fonte ativa; na ausência dela, a configuração mais recente."""
        resposta = (
            supabase.table("workspace_integrations")
            .select("*")
            .eq("workspace_id", workspace_id)
            .execute()
        )
        rows = [
            row for row in (resposta.data or [])
            if str(row.get("provider") or "").lower() in self.SUPPORTED_PROVIDERS
        ]
        rows.sort(
            key=lambda row: (
                row.get("status") == "connected",
                str(row.get("updated_at") or row.get("created_at") or ""),
            ),
            reverse=True,
        )
        return rows[0] if rows else None

    def upsert(
        self,
        workspace_id: str,
        *,
        provider: str,
        adapter_base_url: str,
        adapter_token: str | None = None,
        enabled: bool = True,
    ) -> dict:
        provider = self._provider(provider)
        label = "MercosAdaptor" if provider == "mercos" else "TRAYadaptor"
        base = (adapter_base_url or "").strip().rstrip("/")
        token = (adapter_token or "").strip()
        if not base.startswith(("http://", "https://")):
            raise HTTPException(status_code=400, detail=f"Informe a URL completa do {label}.")

        existing = self.get(workspace_id, provider)
        existing_config = (existing or {}).get("configuration") or {}
        if not isinstance(existing_config, dict):
            existing_config = {}
        if not token:
            token = str(existing_config.get("adapterToken") or "").strip()
        if not token:
            raise HTTPException(status_code=400, detail=f"Informe o token interno do {label}.")

        status = "connected" if enabled else "disconnected"
        configuration = {
            "adapterBaseUrl": base,
            "adapterToken": token,
        }
        payload = {
            "workspace_id": workspace_id,
            "provider": provider,
            "status": status,
            "configuration": configuration,
            "last_error": None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        if enabled:
            for other_provider in self.SUPPORTED_PROVIDERS - {provider}:
                supabase.table("workspace_integrations").update(
                    {"status": "disconnected", "updated_at": datetime.now(timezone.utc).isoformat()}
                ).eq("workspace_id", workspace_id).eq("provider", other_provider).execute()
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

    def upsert_tray(
        self,
        workspace_id: str,
        *,
        adapter_base_url: str,
        adapter_token: str | None = None,
        enabled: bool = True,
    ) -> dict:
        return self.upsert(
            workspace_id,
            provider="tray",
            adapter_base_url=adapter_base_url,
            adapter_token=adapter_token,
            enabled=enabled,
        )

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
            "provider": str(row.get("provider") or "tray"),
            "enabled": row.get("status") == "connected",
            "adapterBaseUrl": config.get("adapterBaseUrl") or "",
            "hasToken": bool(token),
            "status": row.get("status") or "disconnected",
            "lastSyncAt": row.get("last_sync_at"),
            "lastError": row.get("last_error"),
        }

    def client_from_workspace(self, workspace_id: str) -> TrayAdaptorClient:
        row = self.get_configured(workspace_id)
        provider = str((row or {}).get("provider") or "")
        label = "MercosAdaptor" if provider == "mercos" else "TRAYadaptor"
        if not row or row.get("status") != "connected":
            raise HTTPException(
                status_code=400,
                detail="Adaptor comercial não configurado para esta empresa. Aponte a URL no superadmin.",
            )
        config = row.get("configuration") or {}
        base = str(config.get("adapterBaseUrl") or "").strip()
        token = str(config.get("adapterToken") or "").strip()
        if not base or not token:
            raise HTTPException(status_code=400, detail=f"Configuração do {label} incompleta.")
        return TrayAdaptorClient(base, token)

    def test_connection(
        self,
        workspace_id: str | None = None,
        *,
        provider: str | None = None,
        base_url: str | None = None,
        token: str | None = None,
    ) -> dict:
        if workspace_id and not (base_url and token):
            client = self.client_from_workspace(workspace_id)
        else:
            self._provider(provider or "tray")
            if not base_url or not token:
                raise HTTPException(status_code=400, detail="Informe adapterBaseUrl e adapterToken.")
            client = TrayAdaptorClient(base_url, token)
        health = client.health()
        products = client.list_products(page=1, limit=1)
        return {
            "ok": True,
            "provider": provider or str((self.get_configured(workspace_id or "") or {}).get("provider") or "tray"),
            "health": health,
            "sampleProducts": len(products),
        }


workspace_integration_service = WorkspaceIntegrationService()
