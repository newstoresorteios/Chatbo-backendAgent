from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field


class ListQuery(BaseModel):
    page: int = Field(default=1, ge=1)
    pageSize: int = Field(default=50, ge=1, le=200)
    search: str | None = None


class FlexibleModel(BaseModel):
    """Aceita campos extras do front e grava no banco."""

    model_config = ConfigDict(extra="allow")

    def to_db(self, *, exclude_none: bool = True) -> dict[str, Any]:
        return self.model_dump(exclude_none=exclude_none)
