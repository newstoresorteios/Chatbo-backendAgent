from fastapi import HTTPException

from app.repositories.agent_registry_repository import AgentRegistryRepository
from app.schemas.agent_registry import AgentRuntimeConfiguration
from app.services.workspace_service import workspace_service

WORKSPACE_ADMIN_ROLES = {"owner", "admin"}

CONFIG_SCHEMA_VERSION = 1
CONFIG_FIELDS = [
    {"key": "maxReplyChars", "label": "Tamanho máximo da resposta", "description": "Limite de caracteres da resposta final.", "type": "integer", "group": "Respostas", "min": 300, "max": 4000, "step": 100},
    {"key": "historyTurns", "label": "Turnos no histórico", "description": "Quantidade de mensagens anteriores enviadas ao modelo.", "type": "integer", "group": "Contexto", "min": 4, "max": 40, "step": 1},
    {"key": "catalogShortlistSize", "label": "Produtos apresentados", "description": "Máximo de opções mostradas ao cliente por resposta.", "type": "integer", "group": "Catálogo", "min": 1, "max": 5, "step": 1},
    {"key": "catalogCandidatePool", "label": "Candidatos de busca", "description": "Quantidade de produtos avaliados antes do ranqueamento.", "type": "integer", "group": "Catálogo", "min": 5, "max": 80, "step": 5},
    {"key": "catalogRerankLimit", "label": "Candidatos para reranking", "description": "Quantidade de produtos enviados para a seleção final.", "type": "integer", "group": "Catálogo", "min": 5, "max": 20, "step": 1},
    {"key": "observabilityLevel", "label": "Nível dos logs", "description": "Detalhado amplia diagnósticos, mantendo a redação de dados sensíveis.", "type": "select", "group": "Observabilidade", "options": [{"value": "standard", "label": "Padrão"}, {"value": "detailed", "label": "Detalhado"}]},
]


class AgentRegistryService:
    def __init__(self):
        self.repo = AgentRegistryRepository()

    def _missing_schema(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return any(name in text for name in (
            "workspace_agents",
            "agent_runtime_types",
            "workspace_agent_config_versions",
            "publish_workspace_agent_config",
        ))

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
            "configurationVersion": int(row.get("config_version") or 0),
        }

    def _configuration_values(self, row: dict | None) -> AgentRuntimeConfiguration:
        raw = (row or {}).get("configuration") or {}
        runtime = raw.get("runtime", raw) if isinstance(raw, dict) else {}
        values = runtime.get("values") if isinstance(runtime, dict) else {}
        return AgentRuntimeConfiguration.model_validate(values or {})

    def obter_configuracao(self, usuario: dict) -> dict:
        context = workspace_service.get_current_workspace_context(usuario)
        workspace_id = str(context["workspaceId"])
        try:
            row = self.repo.obter_por_workspace(workspace_id)
            values = self._configuration_values(row)
        except Exception as exc:
            if self._missing_schema(exc):
                raise HTTPException(status_code=503, detail="Execute supabase/024_agent_runtime_config.sql no Supabase.") from exc
            raise
        return {
            "schemaVersion": CONFIG_SCHEMA_VERSION,
            "version": int((row or {}).get("config_version") or 0),
            "values": values.model_dump(),
            "fields": CONFIG_FIELDS,
            "updatedAt": (row or {}).get("updated_at"),
        }

    def publicar_configuracao(self, usuario: dict, payload: dict) -> dict:
        context = workspace_service.get_current_workspace_context(usuario)
        if context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar a configuração do agente")
        workspace_id = str(context["workspaceId"])
        values = AgentRuntimeConfiguration.model_validate(payload.get("values") or {})
        try:
            current = self.repo.obter_por_workspace(workspace_id) or {}
            existing = current.get("configuration") or {}
            if not isinstance(existing, dict):
                existing = {}
            configuration = {
                **existing,
                "runtime": {
                    "schemaVersion": CONFIG_SCHEMA_VERSION,
                    "values": values.model_dump(),
                },
            }
            self.repo.publicar_configuracao(
                workspace_id=workspace_id,
                configuration=configuration,
                created_by=str(usuario.get("id") or usuario.get("sub") or ""),
                expected_version=int(payload.get("expectedVersion") or 0),
            )
        except Exception as exc:
            text = str(exc).lower()
            if "config_version_conflict" in text:
                raise HTTPException(status_code=409, detail="A configuração foi alterada por outro operador. Recarregue antes de salvar.") from exc
            if self._missing_schema(exc):
                raise HTTPException(status_code=503, detail="Execute supabase/024_agent_runtime_config.sql no Supabase.") from exc
            raise
        return self.obter_configuracao(usuario)

    def listar_historico_configuracao(self, usuario: dict) -> list[dict]:
        context = workspace_service.get_current_workspace_context(usuario)
        workspace_id = str(context["workspaceId"])
        try:
            rows = self.repo.listar_versoes_configuracao(workspace_id)
        except Exception as exc:
            if self._missing_schema(exc):
                raise HTTPException(status_code=503, detail="Execute supabase/024_agent_runtime_config.sql no Supabase.") from exc
            raise
        return [{
            "id": str(row.get("id")),
            "version": int(row.get("version") or 0),
            "schemaVersion": int(row.get("schema_version") or 1),
            "values": (
                ((row.get("configuration") or {}).get("runtime") or row.get("configuration") or {}).get("values")
                or {}
            ),
            "createdBy": row.get("created_by"),
            "createdAt": row.get("created_at"),
        } for row in rows]

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
                "configurationVersion": 0,
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
            raise HTTPException(
                status_code=400,
                detail="Use /agents/current/configuration para publicar uma configuração validada.",
            )

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
