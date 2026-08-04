from __future__ import annotations

from typing import Any

from fastapi import HTTPException

from app.core.workspace_scope import workspace_id_from_context
from app.repositories.ai.workspace_crud import WorkspaceCrudRepository
from app.services.workspace_service import workspace_service


class WorkspaceCrudService:
    """Service fino: resolve workspace do usuário e delega ao repository."""

    def __init__(self, repo: WorkspaceCrudRepository):
        self.repo = repo

    def _workspace_id(self, usuario: dict) -> str | None:
        if self.repo.workspace_column is None:
            return None
        context = workspace_service.get_current_workspace_context(usuario)
        return workspace_id_from_context(context)

    def listar(
        self,
        usuario: dict,
        *,
        page: int = 1,
        page_size: int = 50,
        filters: dict[str, Any] | None = None,
        search_column: str | None = None,
        search: str | None = None,
    ) -> dict:
        return self.repo.listar(
            self._workspace_id(usuario),
            page=page,
            page_size=page_size,
            filters=filters,
            search_column=search_column,
            search=search,
        )

    def obter(self, usuario: dict, record_id: Any) -> dict:
        row = self.repo.obter(record_id, self._workspace_id(usuario))
        if not row:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return row

    def criar(self, usuario: dict, payload: dict) -> dict:
        return self.repo.criar(payload, self._workspace_id(usuario))

    def atualizar(self, usuario: dict, record_id: Any, payload: dict) -> dict:
        clean = {k: v for k, v in payload.items() if v is not None}
        if not clean:
            return self.obter(usuario, record_id)
        row = self.repo.atualizar(record_id, self._workspace_id(usuario), clean)
        if not row:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return row

    def upsert(self, usuario: dict, payload: dict, *, on_conflict: str) -> dict:
        return self.repo.upsert(payload, self._workspace_id(usuario), on_conflict=on_conflict)

    def obter_por(self, usuario: dict, filters: dict[str, Any]) -> dict:
        row = self.repo.obter_por(self._workspace_id(usuario), filters)
        if not row:
            raise HTTPException(status_code=404, detail="Registro não encontrado")
        return row

    def put_por(self, usuario: dict, filters: dict[str, Any], payload: dict) -> dict:
        """Cria ou atualiza por filtros únicos (ex.: user_id, conversation_key)."""
        workspace_id = self._workspace_id(usuario)
        existing = self.repo.obter_por(workspace_id, filters)
        data = {**payload, **filters}
        if existing:
            record_id = existing.get(self.repo.id_column)
            row = self.repo.atualizar(record_id, workspace_id, data)
            if not row:
                raise HTTPException(status_code=404, detail="Registro não encontrado")
            return row
        return self.repo.criar(data, workspace_id)
