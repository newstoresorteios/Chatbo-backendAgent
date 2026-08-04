"""CRUD genérico com escopo de workspace_id via Supabase."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from app.services.supabase_service import supabase


class WorkspaceCrudRepository:
    def __init__(
        self,
        table: str,
        *,
        id_column: str = "id",
        workspace_column: str | None = "workspace_id",
        order_by: str = "created_at",
        order_desc: bool = True,
        touch_updated_at: bool = True,
    ):
        self.table = table
        self.id_column = id_column
        self.workspace_column = workspace_column
        self.order_by = order_by
        self.order_desc = order_desc
        self.touch_updated_at = touch_updated_at

    def _base(self):
        return supabase.table(self.table)

    def _scoped(self, query, workspace_id: str | None):
        if self.workspace_column and workspace_id:
            return query.eq(self.workspace_column, workspace_id)
        return query

    def listar(
        self,
        workspace_id: str | None,
        *,
        page: int = 1,
        page_size: int = 50,
        filters: dict[str, Any] | None = None,
        search_column: str | None = None,
        search: str | None = None,
    ) -> dict:
        page = max(1, page)
        page_size = min(max(1, page_size), 200)
        start = (page - 1) * page_size
        end = start + page_size - 1

        query = self._base().select("*", count="exact")
        query = self._scoped(query, workspace_id)

        for key, value in (filters or {}).items():
            if value is None or value == "":
                continue
            query = query.eq(key, value)

        if search and search_column:
            query = query.ilike(search_column, f"%{search}%")

        if self.order_by:
            query = query.order(self.order_by, desc=self.order_desc)

        resposta = query.range(start, end).execute()
        items = resposta.data or []
        total = getattr(resposta, "count", None)
        if total is None:
            total = len(items)

        return {
            "items": items,
            "page": page,
            "pageSize": page_size,
            "total": total,
        }

    def obter(self, record_id: Any, workspace_id: str | None) -> dict | None:
        query = self._base().select("*").eq(self.id_column, record_id)
        query = self._scoped(query, workspace_id)
        rows = (query.limit(1).execute().data) or []
        return rows[0] if rows else None

    def criar(self, payload: dict, workspace_id: str | None) -> dict:
        data = dict(payload)
        if self.workspace_column and workspace_id:
            data[self.workspace_column] = workspace_id
        resposta = self._base().insert(data).execute()
        rows = resposta.data or []
        return rows[0] if rows else data

    def atualizar(self, record_id: Any, workspace_id: str | None, payload: dict) -> dict | None:
        data = dict(payload)
        if self.touch_updated_at and "updated_at" not in data:
            data["updated_at"] = datetime.utcnow().isoformat()

        query = self._base().update(data).eq(self.id_column, record_id)
        query = self._scoped(query, workspace_id)
        rows = (query.execute().data) or []
        return rows[0] if rows else None

    def upsert(
        self,
        payload: dict,
        workspace_id: str | None,
        *,
        on_conflict: str,
    ) -> dict:
        data = dict(payload)
        if self.workspace_column and workspace_id:
            data[self.workspace_column] = workspace_id
        if self.touch_updated_at:
            data["updated_at"] = datetime.utcnow().isoformat()
        resposta = self._base().upsert(data, on_conflict=on_conflict).execute()
        rows = resposta.data or []
        return rows[0] if rows else data

    def obter_por(
        self,
        workspace_id: str | None,
        filters: dict[str, Any],
    ) -> dict | None:
        query = self._base().select("*")
        query = self._scoped(query, workspace_id)
        for key, value in filters.items():
            query = query.eq(key, value)
        rows = (query.limit(1).execute().data) or []
        return rows[0] if rows else None
