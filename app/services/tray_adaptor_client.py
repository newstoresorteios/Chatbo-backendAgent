"""Cliente HTTP para o TRAYadaptor (Bearer interno)."""

from __future__ import annotations

import logging
from typing import Any
from urllib.parse import urljoin

import httpx

logger = logging.getLogger(__name__)


def _extract_items(payload: Any, *keys: str) -> list[dict]:
    if isinstance(payload, list):
        return [item for item in payload if isinstance(item, dict)]
    if not isinstance(payload, dict):
        return []
    for key in keys:
        raw = payload.get(key)
        if isinstance(raw, list):
            items: list[dict] = []
            for item in raw:
                if not isinstance(item, dict):
                    continue
                # Tray often wraps: { "Order": {...} }
                nested = next(
                    (item[k] for k in item if isinstance(item.get(k), dict) and k.lower() in {
                        "order", "customer", "product", "variant"
                    }),
                    None,
                )
                items.append(nested if isinstance(nested, dict) else item)
            return items
        if isinstance(raw, dict):
            return [raw]
    # fallback common envelopes
    for key in ("data", "items", "results"):
        raw = payload.get(key)
        if isinstance(raw, list):
            return [item for item in raw if isinstance(item, dict)]
    return []


class TrayAdaptorClient:
    def __init__(self, base_url: str, token: str, *, timeout: float = 60.0) -> None:
        self.base_url = (base_url or "").rstrip("/") + "/"
        self.token = (token or "").strip()
        self.timeout = timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.token}",
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._headers(), params=params or {})
            if response.status_code >= 400:
                raise RuntimeError(f"tray_adaptor_{response.status_code}:{response.text[:300]}")
            if not response.content:
                return {}
            return response.json()

    def health(self) -> dict:
        url = urljoin(self.base_url, "health")
        with httpx.Client(timeout=20.0) as client:
            response = client.get(url)
            if response.status_code >= 400:
                raise RuntimeError(f"tray_health_{response.status_code}")
            try:
                return response.json()
            except Exception:
                return {"ok": True, "status_code": response.status_code}

    def list_orders(self, *, page: int = 1, limit: int = 50) -> list[dict]:
        payload = self._get("internal/orders", {"page": page, "limit": limit})
        return _extract_items(payload, "Orders", "Order", "orders", "order")

    def list_customers(self, *, page: int = 1, limit: int = 50) -> list[dict]:
        payload = self._get("internal/customers", {"page": page, "limit": limit})
        return _extract_items(payload, "Customers", "Customer", "customers", "customer")

    def list_products(self, *, page: int = 1, limit: int = 50) -> list[dict]:
        payload = self._get("internal/products", {"page": page, "limit": limit})
        return _extract_items(payload, "Products", "Product", "products", "product")

    def collect_sample(self, *, max_pages: int = 3, page_size: int = 50) -> dict[str, Any]:
        orders: list[dict] = []
        customers: list[dict] = []
        products: list[dict] = []
        for page in range(1, max_pages + 1):
            batch = self.list_orders(page=page, limit=page_size)
            orders.extend(batch)
            if len(batch) < page_size:
                break
        for page in range(1, max_pages + 1):
            batch = self.list_customers(page=page, limit=page_size)
            customers.extend(batch)
            if len(batch) < page_size:
                break
        for page in range(1, min(max_pages, 2) + 1):
            batch = self.list_products(page=page, limit=page_size)
            products.extend(batch)
            if len(batch) < page_size:
                break
        return {
            "orders": orders,
            "customers": customers,
            "products": products,
            "pagesFetched": {
                "orders": min(max_pages, max(1, (len(orders) + page_size - 1) // page_size)),
                "customers": min(max_pages, max(1, (len(customers) + page_size - 1) // page_size)),
                "products": min(2, max(1, (len(products) + page_size - 1) // page_size)),
            },
        }
