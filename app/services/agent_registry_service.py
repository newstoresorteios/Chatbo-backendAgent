from fastapi import HTTPException

from app.repositories.agent_registry_repository import AgentRegistryRepository
from app.services.workspace_service import workspace_service

WORKSPACE_ADMIN_ROLES = {"owner", "admin"}


class AgentRegistryService:
    def __init__(self):
        self.repo = AgentRegistryRepository()

    def _missing_schema(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return "workspace_agents" in text or "agent_runtime_types" in text

    def _map(self, row: dict | None, workspace_id: str) -> dict | None:
        if not row:
            return None
        tipo = row.get("agent_runtime_types") or {}
        if isinstance(tipo, list):
            tipo = tipo[0] if tipo else {}
        agent_type = row.get("agent_type") or tipo.get("code") or "nsagent"
        return {
            "id": str(row.get("id")),
            "companyId": workspace_id,
            "workspaceId": workspace_id,
            "agentType": agent_type,
            "baseRuntime": tipo.get("base_runtime") or ("agentia" if agent_type.startswith("agentia") else "nsagent"),
            "status": row.get("status") or "active",
            "displayName": row.get("display_name"),
            "configuration": row.get("configuration") or {},
        }

    def listar_tipos(self) -> list[dict]:
        try:
            rows = self.repo.listar_tipos()
        except Exception as exc:
            if self._missing_schema(exc):
                raise HTTPException(
                    status_code=503,
                    detail="Execute supabase/020_company_agents.sql no Supabase.",
                ) from exc
            raise
        return [
            {
                "code": row.get("code"),
                "name": row.get("name"),
                "baseRuntime": row.get("base_runtime"),
                "description": row.get("description"),
            }
            for row in rows
        ]

    def obter_agente_empresa(self, usuario: dict) -> dict:
        context = workspace_service.get_current_workspace_context(usuario)
        workspace_id = str(context["workspaceId"])
        try:
            row = self.repo.obter_por_workspace(workspace_id)
        except Exception as exc:
            if self._missing_schema(exc):
                raise HTTPException(
                    status_code=503,
                    detail="Execute supabase/020_company_agents.sql no Supabase.",
                ) from exc
            raise
        mapped = self._map(row, workspace_id)
        if not mapped:
            mapped = {
                "id": "",
                "companyId": workspace_id,
                "workspaceId": workspace_id,
                "agentType": "nsagent",
                "baseRuntime": "nsagent",
                "status": "provisioning",
                "displayName": context.get("workspaceName"),
                "configuration": {},
            }
        return mapped

    def atualizar_agente_empresa(self, usuario: dict, payload: dict) -> dict:
        context = workspace_service.get_current_workspace_context(usuario)
        if context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar o agente da empresa")
        workspace_id = str(context["workspaceId"])

        update: dict = {}
        if payload.get("agentType") is not None:
            code = str(payload["agentType"]).strip()
            tipo = self.repo.obter_tipo(code)
            if not tipo:
                raise HTTPException(status_code=400, detail=f"Tipo de agente inválido: {code}")
            update["agent_type"] = code
        if payload.get("status") is not None:
            update["status"] = payload["status"]
        if payload.get("displayName") is not None:
            update["display_name"] = str(payload["displayName"] or "").strip() or None
        if payload.get("configuration") is not None:
            if not isinstance(payload["configuration"], dict):
                raise HTTPException(status_code=400, detail="configuration deve ser um objeto")
            update["configuration"] = payload["configuration"]

        if not update:
            return self.obter_agente_empresa(usuario)

        try:
            self.repo.upsert(workspace_id, update)
        except Exception as exc:
            if self._missing_schema(exc):
                raise HTTPException(
                    status_code=503,
                    detail="Execute supabase/020_company_agents.sql no Supabase.",
                ) from exc
            raise
        return self.obter_agente_empresa(usuario)

    def obter_runtime_interno(self, workspace_id: str) -> dict:
        from app.repositories.workspace_repository import WorkspaceRepository

        workspace = WorkspaceRepository().buscar_workspace(workspace_id)
        if not workspace:
            raise HTTPException(status_code=404, detail="Empresa não encontrada")
        row = self.repo.obter_por_workspace(workspace_id)
        mapped = self._map(row, workspace_id)
        if not mapped:
            raise HTTPException(status_code=404, detail="Agente da empresa não configurado")
        return {
            **mapped,
            "companyId": workspace_id,
            "companyName": workspace.get("name"),
            "brandName": workspace.get("brand_name"),
        }


agent_registry_service = AgentRegistryService()
