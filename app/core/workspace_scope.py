"""Escopo multi-empresa: company_id (API) == workspace_id (banco)."""

from __future__ import annotations

from fastapi import Depends, HTTPException

from app.core.auth import obter_usuario_atual


def company_id_from_context(context: dict) -> str:
    """Alias estável: companyId === workspaceId."""
    company_id = context.get("companyId") or context.get("workspaceId")
    if not company_id:
        raise HTTPException(status_code=403, detail="Empresa não resolvida para o usuário")
    return str(company_id)


def workspace_id_from_context(context: dict) -> str:
    return company_id_from_context(context)


def apply_workspace_filter(query, workspace_id: str, column: str = "workspace_id"):
    """Filtra linhas da empresa. Exclui legado sem workspace_id."""
    return query.eq(column, workspace_id)


def stamp_workspace(payload: dict, workspace_id: str) -> dict:
    return {**payload, "workspace_id": workspace_id}


def obter_company_context(usuario: dict = Depends(obter_usuario_atual)) -> dict:
    from app.services.workspace_service import workspace_service

    context = workspace_service.get_current_workspace_context(usuario)
    company_id = str(context["workspaceId"])
    return {
        **context,
        "companyId": company_id,
        "workspaceId": company_id,
    }
