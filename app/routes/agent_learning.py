"""Rotas de aprendizado do agente (gate humano para persona)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, Field

from app.core.permissions import requer_permissao
from app.services.agent_learning_service import agent_learning_service
from app.services.workspace_service import workspace_service

router = APIRouter()


class PromoteRequest(BaseModel):
    activate: bool = Field(
        default=True,
        description="Se true, promove e ativa na persona (equivale a authorize+promote).",
    )


class RejectRequest(BaseModel):
    reason: str | None = Field(default=None, max_length=500)


def _actor(usuario: dict) -> str:
    return str(usuario.get("email") or usuario.get("id") or "chatbo_ui")


def _workspace_id(usuario: dict) -> str:
    context = workspace_service.get_current_workspace_context(usuario)
    return str(context["workspaceId"])


@router.get("/agent-learning/overview")
def learning_overview(usuario: dict = Depends(requer_permissao("managePlatform"))):
    _ = usuario
    try:
        return agent_learning_service.overview()
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/agent-learning/insights")
def list_learning_insights(
    status: str | None = Query(default="pending_review"),
    limit: int = Query(default=50, ge=1, le=200),
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    _ = usuario
    try:
        return agent_learning_service.list_insights(status=status, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.get("/agent-learning/extensions")
def list_learning_extensions(
    status: str | None = Query(default="pending_review"),
    limit: int = Query(default=50, ge=1, le=200),
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    _ = usuario
    try:
        return agent_learning_service.list_extensions(status=status, limit=limit)
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/agent-learning/insights/{insight_id}/promote")
def promote_learning_insight(
    insight_id: int,
    body: PromoteRequest | None = None,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    activate = True if body is None else bool(body.activate)
    try:
        return agent_learning_service.promote_insight(
            insight_id,
            activate=activate,
            workspace_id=_workspace_id(usuario),
            actor=_actor(usuario),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/agent-learning/insights/{insight_id}/reject")
def reject_learning_insight(
    insight_id: int,
    body: RejectRequest | None = None,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    try:
        return agent_learning_service.reject_insight(
            insight_id,
            reason=body.reason if body else None,
            actor=_actor(usuario),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/agent-learning/extensions/{extension_id}/approve")
def approve_learning_extension(
    extension_id: int,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    try:
        return agent_learning_service.approve_extension(
            extension_id,
            actor=_actor(usuario),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc


@router.post("/agent-learning/extensions/{extension_id}/reject")
def reject_learning_extension(
    extension_id: int,
    body: RejectRequest | None = None,
    usuario: dict = Depends(requer_permissao("managePlatform")),
):
    try:
        return agent_learning_service.reject_extension(
            extension_id,
            reason=body.reason if body else None,
            actor=_actor(usuario),
        )
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=502, detail=str(exc)) from exc
