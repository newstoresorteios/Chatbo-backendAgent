"""Cliente HTTP para o TRAYadaptor (Bearer interno)."""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any, Callable
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
                    (
                        item[k]
                        for k in item
                        if isinstance(item.get(k), dict)
                        and k.lower() in {"order", "customer", "product", "variant"}
                    ),
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


def _parse_dt(value: Any) -> datetime | None:
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    text = str(value).strip()
    if not text or text.startswith("0000-00-00"):
        return None
    text = text.replace("Z", "+00:00")
    for fmt in (
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%d %H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
        "%d/%m/%Y %H:%M:%S",
        "%d/%m/%Y",
    ):
        try:
            parsed = datetime.strptime(text, fmt)
            return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
        except ValueError:
            continue
    try:
        parsed = datetime.fromisoformat(text)
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _row_date(row: dict, *keys: str) -> datetime | None:
    for key in keys:
        parsed = _parse_dt(row.get(key))
        if parsed is not None:
            return parsed
    return None


def _in_period(row: dict, start: datetime, end: datetime, *keys: str) -> bool:
    parsed = _row_date(row, *keys)
    if parsed is None:
        return True
    return start <= parsed <= end


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

    def list_orders(self, *, page: int = 1, limit: int = 50, **filters: Any) -> list[dict]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        for key, value in filters.items():
            if value is not None and value != "":
                params[key] = value
        payload = self._get("internal/orders", params)
        return _extract_items(payload, "Orders", "Order", "orders", "order")

    def list_customers(self, *, page: int = 1, limit: int = 50, **filters: Any) -> list[dict]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        for key, value in filters.items():
            if value is not None and value != "":
                params[key] = value
        payload = self._get("internal/customers", params)
        return _extract_items(payload, "Customers", "Customer", "customers", "customer")

    def list_products(self, *, page: int = 1, limit: int = 50, **filters: Any) -> list[dict]:
        params: dict[str, Any] = {"page": page, "limit": limit}
        for key, value in filters.items():
            if value is not None and value != "":
                params[key] = value
        payload = self._get("internal/products", params)
        return _extract_items(payload, "Products", "Product", "products", "product")

    def _paginate(
        self,
        fetcher: Callable[..., list[dict]],
        *,
        page_size: int,
        max_pages: int,
        filters: dict[str, Any] | None = None,
        keep_row: Callable[[dict], bool] | None = None,
        stop_when_older: Callable[[dict], bool] | None = None,
    ) -> tuple[list[dict], int]:
        rows: list[dict] = []
        pages = 0
        filters = filters or {}
        for page in range(1, max_pages + 1):
            batch = fetcher(page=page, limit=page_size, **filters)
            pages = page
            if not batch:
                break
            older_streak = 0
            for row in batch:
                if keep_row is None or keep_row(row):
                    rows.append(row)
                    older_streak = 0
                elif stop_when_older and stop_when_older(row):
                    older_streak += 1
                else:
                    older_streak = 0
            if stop_when_older and batch and older_streak == len(batch) and rows:
                break
            if len(batch) < page_size:
                break
        return rows, pages

    def collect_sample(self, *, max_pages: int = 3, page_size: int = 50) -> dict[str, Any]:
        """Compat: amostra curta (legado). Prefira collect_period."""
        return self.collect_period(period_days=30, max_pages=max_pages, page_size=page_size)

    def collect_period(
        self,
        *,
        period_days: int = 30,
        page_size: int = 50,
        max_pages: int = 40,
        product_pages: int = 2,
        customer_pages: int = 6,
    ) -> dict[str, Any]:
        """Carrega pedidos do período (padrão 30 dias) via TRAYadaptor.

        Tray aceita filtro clássico `date=YYYY-MM-DD,YYYY-MM-DD` em /orders.
        """
        days = max(1, int(period_days or 30))
        end = datetime.now(timezone.utc)
        start = end - timedelta(days=days)
        start_day = start.date().isoformat()
        end_day = end.date().isoformat()

        order_date_keys = ("date", "created", "modified", "payment_date", "created_at")
        order_filters = {"date": f"{start_day},{end_day}"}

        def keep_order(row: dict) -> bool:
            return _in_period(row, start, end, *order_date_keys)

        def older_order(row: dict) -> bool:
            parsed = _row_date(row, *order_date_keys)
            return parsed is not None and parsed < start

        try:
            orders, order_pages = self._paginate(
                self.list_orders,
                page_size=page_size,
                max_pages=max_pages,
                filters=order_filters,
                keep_row=keep_order,
                stop_when_older=older_order,
            )
            filters_used = order_filters
        except Exception as exc:
            logger.warning("Filtro date de pedidos falhou (%s); paginando sem filtro.", exc)
            orders, order_pages = self._paginate(
                self.list_orders,
                page_size=page_size,
                max_pages=max_pages,
                filters=None,
                keep_row=keep_order,
                stop_when_older=older_order,
            )
            filters_used = {}

        customers, customer_pages_fetched = self._paginate(
            self.list_customers,
            page_size=page_size,
            max_pages=customer_pages,
            filters=None,
        )
        products, product_pages_fetched = self._paginate(
            self.list_products,
            page_size=page_size,
            max_pages=product_pages,
            filters=None,
        )

        return {
            "orders": orders,
            "customers": customers,
            "products": products,
            "period": {
                "days": days,
                "start": start.isoformat(),
                "end": end.isoformat(),
                "startDate": start_day,
                "endDate": end_day,
            },
            "pagesFetched": {
                "orders": order_pages,
                "customers": customer_pages_fetched,
                "products": product_pages_fetched,
            },
            "filtersUsed": {
                "orders": filters_used,
                "customers": {},
            },
            "rawCounts": {
                "ordersInPeriod": len(orders),
                "customersInPeriod": len(customers),
                "products": len(products),
            },
        }
