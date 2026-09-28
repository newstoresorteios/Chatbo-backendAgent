"""Cliente HTTP para o MercosAdaptor (header interno ``x-api-key``)."""

from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import httpx

from app.services.tray_adaptor_client import TrayAdaptorClient, _extract_items


class MercosAdaptorClient(TrayAdaptorClient):
    """Adapta o contrato cursor-based do MercosAdaptor ao coletor comercial."""

    def __init__(self, base_url: str, token: str, *, timeout: float = 60.0) -> None:
        super().__init__(base_url, token, timeout=timeout)
        self._resource_cache: dict[str, list[dict]] = {}

    def _headers(self) -> dict[str, str]:
        return {
            "x-api-key": self.token,
            "Accept": "application/json",
        }

    def _get(self, path: str, params: dict | None = None) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        with httpx.Client(timeout=self.timeout) as client:
            response = client.get(url, headers=self._headers(), params=params or {})
            if response.status_code >= 400:
                raise RuntimeError(f"mercos_adaptor_{response.status_code}:{response.text[:300]}")
            if not response.content:
                return {}
            return response.json()

    def health(self) -> dict:
        payload = self._get("health")
        return payload if isinstance(payload, dict) else {"ok": True}

    def _resource(self, resource: str, **filters: Any) -> list[dict]:
        altered_after = str(filters.get("alterado_apos") or "").strip()
        cache_key = f"{resource}:{altered_after}"
        if cache_key not in self._resource_cache:
            params = {"alterado_apos": altered_after} if altered_after else None
            payload = self._get(f"v1/{resource}", params)
            self._resource_cache[cache_key] = _extract_items(payload, "data")
        return self._resource_cache[cache_key]

    @staticmethod
    def _page(rows: list[dict], page: int, limit: int) -> list[dict]:
        start = max(0, int(page) - 1) * max(1, int(limit))
        return rows[start:start + max(1, int(limit))]

    def list_orders(self, *, page: int = 1, limit: int = 50, **filters: Any) -> list[dict]:
        rows = []
        for order in self._resource("orders", **filters):
            rows.append({
                **order,
                "date": order.get("data_emissao") or order.get("data_criacao") or order.get("ultima_alteracao"),
                "customer_name": order.get("cliente_nome_fantasia") or order.get("cliente_razao_social") or order.get("contato_nome"),
                "customer_email": order.get("cliente_email"),
                "customer_phone": order.get("cliente_telefone"),
            })
        return self._page(rows, page, limit)

    def list_customers(self, *, page: int = 1, limit: int = 50, **filters: Any) -> list[dict]:
        return self._page(self._resource("customers", **filters), page, limit)

    def list_products(self, *, page: int = 1, limit: int = 50, **filters: Any) -> list[dict]:
        return self._page(self._resource("products", **filters), page, limit)

    def _hydrate_order_customers(self, orders: list[dict], *, max_customers: int = 86) -> list[dict]:
        # A listagem MercosAdaptor já inclui telefone, e-mail e nome do cliente.
        return orders

    def order_complete(self, order_id: str) -> dict:
        # Em produção a API Mercos não permite GET de pedido por ID. A listagem
        # do adaptor já entrega os itens completos, então reutilizamos o cache.
        orders = self._resource("orders")
        order = next((row for row in orders if str(row.get("id")) == str(order_id)), {})
        products = []
        for item in order.get("itens") or []:
            if not isinstance(item, dict):
                continue
            products.append({
                "product_id": item.get("produto_id"),
                "name": item.get("produto_nome") or item.get("produto_codigo"),
                "quantity": item.get("quantidade") or 1,
                "price": item.get("preco_liquido") or item.get("preco_tabela") or 0,
            })
        return {"products": products}
