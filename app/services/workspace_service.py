from datetime import datetime
import logging

from fastapi import HTTPException

from app.repositories.catalog_repository import CatalogRepository
from app.repositories.settings_repository import SettingsRepository
from app.repositories.persona_repository import PersonaRepository
from app.repositories.workspace_repository import WorkspaceRepository

logger = logging.getLogger(__name__)

WORKSPACE_ADMIN_ROLES = {"owner", "admin"}
WORKSPACE_VIEW_ROLES = {"owner", "admin", "supervisor"}
ONBOARDING_STATUSES = {"pending", "in_progress", "complete"}
ONBOARDING_PATCH_STATUSES = {"pending", "in_progress"}
SALES_MODELS = {"b2b", "b2c", "mixed"}
ONBOARDING_STEPS = ("empresa", "operacao", "catalogo", "canais", "persona", "teste", "ativacao")
LEGACY_STEP_MAP = {"business": "empresa", "operation": "operacao", "catalog": "catalogo", "channels": "canais", "activation": "ativacao"}


class WorkspaceService:
    def __init__(self):
        self.repo = WorkspaceRepository()
        self.settings_repo = SettingsRepository()
        self.persona_repo = PersonaRepository()
        self.catalog_repo = CatalogRepository()

    def _missing_schema(self, exc: Exception) -> bool:
        text = str(exc).lower()
        return any(name in text for name in ("workspace_members", "workspaces", "workspace_settings", "workspace_onboarding"))

    def get_current_workspace_context(self, usuario: dict) -> dict:
        account_type = usuario.get("account_type") if usuario.get("account_type") == "system_admin" else "workspace_user"
        try:
            membership = self.repo.buscar_membership_ativo(str(usuario.get("id")))
        except Exception as exc:
            if self._missing_schema(exc):
                raise HTTPException(status_code=503, detail="Execute supabase/014_workspace_foundation.sql no Supabase.") from exc
            raise
        if not membership:
            raise HTTPException(status_code=403, detail="Usuário não pertence a um workspace ativo")
        workspace = membership.get("workspaces") or self.repo.buscar_workspace(str(membership.get("workspace_id")))
        if not workspace:
            raise HTTPException(status_code=404, detail="Workspace não encontrado")
        if workspace.get("status") != "active":
            raise HTTPException(status_code=403, detail="Workspace inativo")
        onboarding = self.repo.obter_onboarding(str(workspace.get("id"))) or {}
        return {"workspaceId": str(workspace.get("id")), "workspaceName": workspace.get("name") or usuario.get("empresa") or "NITRUS", "workspaceRole": membership.get("role") or "member", "onboardingStatus": onboarding.get("status") or "complete", "accountType": account_type}

    def criar_workspace_inicial(self, *, user_id: str, name: str) -> dict:
        workspace = self.repo.criar_workspace(name=name)
        workspace_id = str(workspace.get("id"))
        try:
            self.repo.criar_membership(workspace_id=workspace_id, user_id=user_id, role="owner")
            self.repo.criar_settings(workspace_id, {"currency": "BRL", "primary_contact": None})
            self.repo.criar_onboarding(workspace_id, status="pending", current_step="empresa")
            try:
                from app.services.billing_service import billing_service
                billing_service.criar_trial(workspace_id, user_id)
            except Exception:
                logger.exception("Não foi possível criar o trial do workspace %s; cadastro preservado.", workspace_id)
        except Exception:
            self.repo.excluir_workspace(workspace_id)
            raise
        return workspace

    def excluir_workspace(self, workspace_id: str) -> None:
        self.repo.excluir_workspace(workspace_id)

    def _settings_response(self, row: dict | None) -> dict:
        row = row or {}
        channels = row.get("sales_channels") or []
        return {"segment": row.get("segment"), "website": row.get("website"), "country": row.get("country"), "currency": row.get("currency"), "salesModel": row.get("sales_model"), "salesChannels": channels if isinstance(channels, list) else [], "businessHours": row.get("business_hours"), "primaryContact": row.get("primary_contact"), "agentDisplayName": row.get("agent_display_name"), "agentRole": row.get("agent_role"), "agentLanguage": row.get("agent_language"), "agentPrimaryChannel": row.get("agent_primary_channel")}

    def obter_workspace_atual(self, usuario: dict) -> dict:
        context = self.get_current_workspace_context(usuario)
        workspace = self.repo.buscar_workspace(context["workspaceId"]) or {}
        return {"id": context["workspaceId"], "name": workspace.get("name") or context["workspaceName"], "brandName": workspace.get("brand_name"), "role": context["workspaceRole"], "status": workspace.get("status", "active"), "accountType": context["accountType"], "onboardingStatus": context["onboardingStatus"], "settings": self._settings_response(self.repo.obter_settings(context["workspaceId"]))}

    def _legacy_empresa(self) -> dict:
        try:
            return self.settings_repo.obter_empresa() or {}
        except Exception:
            return {}

    def obter_empresa_settings(self, usuario: dict) -> dict:
        context = self.get_current_workspace_context(usuario)
        workspace = self.repo.buscar_workspace(context["workspaceId"]) or {}
        settings = self.repo.obter_settings(context["workspaceId"]) or {}
        legacy = self._legacy_empresa()
        return {"name": workspace.get("name") or legacy.get("nome") or "NITRUS", "brandName": workspace.get("brand_name") or "", "cnpj": settings.get("cnpj") or legacy.get("cnpj") or "", "email": settings.get("primary_contact") or legacy.get("email") or "", "phone": settings.get("phone") or legacy.get("telefone") or "", **self._settings_response(settings)}

    def _require_view(self, context: dict) -> None:
        if context.get("workspaceRole") not in WORKSPACE_VIEW_ROLES:
            raise HTTPException(status_code=403, detail="Você não possui permissão para visualizar o onboarding")

    def _require_workspace_admin(self, context: dict) -> None:
        if context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Você não possui permissão para alterar o onboarding")

    def salvar_empresa_settings(self, usuario: dict, payload: dict) -> dict:
        context = self.get_current_workspace_context(usuario)
        self._require_workspace_admin(context)
        update = {}
        if payload.get("name") is not None:
            name = str(payload.get("name") or "").strip()
            if not name:
                raise HTTPException(status_code=400, detail="Nome da empresa é obrigatório")
            update["name"] = name
        if payload.get("brandName") is not None:
            update["brand_name"] = str(payload.get("brandName") or "").strip() or None
        if update:
            self.repo.atualizar_workspace(context["workspaceId"], update)
        model = payload.get("salesModel")
        if model and model not in SALES_MODELS:
            raise HTTPException(status_code=400, detail="Modelo de vendas inválido")
        mapping = {"segment": "segment", "website": "website", "country": "country", "currency": "currency", "salesModel": "sales_model", "salesChannels": "sales_channels", "businessHours": "business_hours", "primaryContact": "primary_contact", "email": "primary_contact", "agentDisplayName": "agent_display_name", "agentRole": "agent_role", "agentLanguage": "agent_language", "agentPrimaryChannel": "agent_primary_channel", "cnpj": "cnpj", "phone": "phone"}
        values = {dest: payload.get(src) for src, dest in mapping.items() if payload.get(src) is not None}
        if values:
            self.repo.salvar_settings(context["workspaceId"], values)
        return self.obter_empresa_settings(usuario)

    def _company_configured(self, workspace: dict, settings: dict) -> bool:
        legacy = self._legacy_empresa()
        name = workspace.get("brand_name") or workspace.get("name") or legacy.get("nome")
        return bool(str(name or "").strip() and str(settings.get("country") or "").strip() and str(settings.get("currency") or "").strip() and str(settings.get("segment") or "").strip())

    def _operation_configured(self, settings: dict) -> bool:
        return bool(settings.get("sales_model") in SALES_MODELS and isinstance(settings.get("sales_channels"), list) and settings.get("sales_channels") and str(settings.get("business_hours") or "").strip() and str(settings.get("primary_contact") or "").strip())

    def _catalog(self) -> dict:
        try:
            count = self.catalog_repo.contar_produtos()
        except Exception:
            count = 0
        return {"catalogAvailable": count > 0, "catalogScope": "legacy_global" if count > 0 else "none", "catalogProductCount": count}

    def _requirements(self, workspace_id: str) -> dict:
        workspace = self.repo.buscar_workspace(workspace_id) or {}
        settings = self.repo.obter_settings(workspace_id) or {}
        personas = self.persona_repo.listar_por_workspace(workspace_id)
        active = [row for row in personas if row.get("status") == "active"]
        active_persona = active[0] if len(active) == 1 else None
        channels = self.repo.listar_canais(workspace_id)
        channel_configured = any(row.get("status") in {"configured", "active"} for row in channels)
        catalog = self._catalog()
        test_completed = bool(active_persona and self.repo.ultimo_teste_sucesso(workspace_id, str(active_persona.get("id"))))
        return {"companyConfigured": self._company_configured(workspace, settings), "operationConfigured": self._operation_configured(settings), **catalog, "channelConfigured": channel_configured, "personaCreated": bool(personas), "personaActive": bool(active_persona), "testCompleted": test_completed, "readyForActivation": bool(self._company_configured(workspace, settings) and self._operation_configured(settings) and catalog["catalogAvailable"] and channel_configured and active_persona and test_completed)}

    def _onboarding_response(self, row: dict | None, workspace_id: str) -> dict:
        row = row or {}
        completed = [LEGACY_STEP_MAP.get(step, step) for step in (row.get("completed_steps") or []) if step in ONBOARDING_STEPS or step in LEGACY_STEP_MAP]
        requirements = self._requirements(workspace_id)
        current = LEGACY_STEP_MAP.get(row.get("current_step"), row.get("current_step"))
        if not current:
            current = next((step for step in ONBOARDING_STEPS if not self._step_requirement(step, requirements)), "ativacao")
        return {"status": row.get("status") or "pending", "currentStep": current, "completedSteps": completed, "requirements": requirements, "startedAt": row.get("started_at"), "completedAt": row.get("completed_at")}

    def _step_requirement(self, step: str, req: dict) -> bool:
        return {"empresa": req["companyConfigured"], "operacao": req["operationConfigured"], "catalogo": req["catalogAvailable"], "canais": req["channelConfigured"], "persona": req["personaActive"], "teste": req["testCompleted"], "ativacao": req["readyForActivation"]}.get(step, False)

    def obter_onboarding(self, usuario: dict) -> dict:
        context = self.get_current_workspace_context(usuario)
        self._require_view(context)
        row = self.repo.obter_onboarding(context["workspaceId"])
        if not row:
            raise HTTPException(status_code=404, detail="Onboarding não encontrado")
        return self._onboarding_response(row, context["workspaceId"])

    def atualizar_onboarding(self, usuario: dict, payload: dict) -> dict:
        context = self.get_current_workspace_context(usuario)
        self._require_workspace_admin(context)
        status = payload.get("status")
        if status and status not in ONBOARDING_PATCH_STATUSES:
            raise HTTPException(status_code=400, detail="Use /onboarding/activate para concluir o onboarding")
        data = {"current_step": payload.get("currentStep")} if payload.get("currentStep") is not None else {}
        if status is not None:
            data["status"] = status
        if data:
            self.repo.salvar_onboarding(context["workspaceId"], data)
        return self.obter_onboarding(usuario)

    def listar_canais(self, usuario: dict) -> list[dict]:
        context = self.get_current_workspace_context(usuario)
        self._require_view(context)
        return [self._channel_response(row) for row in self.repo.listar_canais(context["workspaceId"])]

    def salvar_canal(self, usuario: dict, payload: dict) -> dict:
        context = self.get_current_workspace_context(usuario)
        self._require_workspace_admin(context)
        channel_type = payload.get("channelType")
        if channel_type not in {"whatsapp", "webchat"}:
            raise HTTPException(status_code=400, detail="Canal não suportado nesta etapa")
        status = payload.get("status") or "configured"
        if status not in {"draft", "configured", "inactive"}:
            raise HTTPException(status_code=400, detail="Status de canal inválido")
        row = self.repo.salvar_canal(context["workspaceId"], channel_type, {"status": status, "configuration": payload.get("configuration") or {}, "updated_at": datetime.utcnow().isoformat()})
        return self._channel_response(row)

    def _channel_response(self, row: dict) -> dict:
        return {"id": str(row.get("id")), "workspaceId": str(row.get("workspace_id")), "channelType": row.get("channel_type"), "status": row.get("status"), "configuration": row.get("configuration") or {}, "createdAt": row.get("created_at"), "updatedAt": row.get("updated_at")}

    def testar_onboarding(self, usuario: dict, input_text: str) -> dict:
        context = self.get_current_workspace_context(usuario)
        self._require_view(context)
        active = self.persona_repo.buscar_ativa(context["workspaceId"])
        if not active:
            raise HTTPException(status_code=422, detail="Ative uma Persona antes de executar o teste.")
        now = datetime.utcnow().isoformat()
        try:
            from app.services.persona_service import persona_service
            result = persona_service.testar(usuario, {"persona": persona_service._response(active), "customerMessage": input_text})
            self.repo.registrar_onboarding_test({"workspace_id": context["workspaceId"], "persona_id": active["id"], "status": "success", "input_text": input_text, "output_preview": str(result.get("response") or "")[:1000], "completed_at": now, "created_by": str(usuario.get("id")), "created_at": now})
            return {**result, "personaId": str(active["id"]), "testCompleted": True}
        except HTTPException as exc:
            self.repo.registrar_onboarding_test({"workspace_id": context["workspaceId"], "persona_id": active["id"], "status": "failed", "input_text": input_text, "error_message": str(exc.detail)[:1000], "created_by": str(usuario.get("id")), "created_at": now})
            raise
        except Exception as exc:
            self.repo.registrar_onboarding_test({"workspace_id": context["workspaceId"], "persona_id": active["id"], "status": "failed", "input_text": input_text, "error_message": str(exc)[:1000], "created_by": str(usuario.get("id")), "created_at": now})
            raise HTTPException(status_code=503, detail="Não foi possível executar o teste do onboarding.") from exc

    def ativar_onboarding(self, usuario: dict) -> dict:
        context = self.get_current_workspace_context(usuario)
        self._require_workspace_admin(context)
        requirements = self._requirements(context["workspaceId"])
        missing = [key for key in ("companyConfigured", "operationConfigured", "catalogAvailable", "channelConfigured", "personaActive", "testCompleted") if not requirements[key]]
        if missing:
            raise HTTPException(status_code=409, detail={"message": "Onboarding incompleto.", "missingRequirements": missing})
        self.repo.salvar_onboarding(context["workspaceId"], {"status": "complete", "current_step": "ativacao", "completed_steps": list(ONBOARDING_STEPS), "completed_at": datetime.utcnow().isoformat()})
        return self.obter_onboarding(usuario)

    def concluir_onboarding(self, usuario: dict) -> dict:
        self.ativar_onboarding(usuario)
        return self.obter_workspace_atual(usuario)


workspace_service = WorkspaceService()
