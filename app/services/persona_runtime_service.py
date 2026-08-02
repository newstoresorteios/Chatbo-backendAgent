import logging
from time import perf_counter
from typing import Any

from fastapi import HTTPException

from app.repositories.persona_repository import PersonaRepository
from app.repositories.workspace_repository import WorkspaceRepository
from app.schemas.persona_runtime import ActivePersonaRuntime, PersonaRuntimeExample


logger = logging.getLogger(__name__)


class PersonaRuntimeService:
    def __init__(
        self,
        persona_repo: PersonaRepository | None = None,
        workspace_repo: WorkspaceRepository | None = None,
    ):
        self.persona_repo = persona_repo or PersonaRepository()
        self.workspace_repo = workspace_repo or WorkspaceRepository()

    @staticmethod
    def _text(value: Any) -> str | None:
        if value is None:
            return None
        if not isinstance(value, str):
            return None
        value = value.strip()
        return value or None

    @classmethod
    def _rules(cls, value: Any) -> list[str | dict[str, Any]]:
        if not isinstance(value, list):
            return []
        result: list[str | dict[str, Any]] = []
        for item in value:
            if isinstance(item, str):
                item = item.strip()
                if item:
                    result.append(item)
            elif isinstance(item, dict):
                result.append(item)
        return result

    @classmethod
    def _object(cls, value: Any) -> dict[str, Any]:
        return dict(value) if isinstance(value, dict) else {}

    @classmethod
    def _examples(cls, value: Any) -> list[PersonaRuntimeExample]:
        if not isinstance(value, list):
            return []
        result: list[PersonaRuntimeExample] = []
        for item in value:
            if not isinstance(item, dict):
                continue
            customer_message = cls._text(item.get("customerMessage") or item.get("customer_message"))
            expected_response = cls._text(item.get("expectedResponse") or item.get("expected_response"))
            if customer_message and expected_response:
                result.append(PersonaRuntimeExample(
                    customerMessage=customer_message,
                    expectedResponse=expected_response,
                ))
        return result

    @classmethod
    def _runtime(cls, row: dict[str, Any], workspace_id: str) -> ActivePersonaRuntime:
        return ActivePersonaRuntime(
            personaId=str(row.get("id")),
            workspaceId=workspace_id,
            version=int(row.get("version") or 1),
            name=cls._text(row.get("name")),
            role=cls._text(row.get("role")),
            language=cls._text(row.get("language")),
            tone=cls._text(row.get("tone")),
            greeting=cls._text(row.get("greeting")),
            introduction=cls._text(row.get("introduction")),
            customerAddressStyle=cls._text(row.get("customer_address_style")),
            closingMessage=cls._text(row.get("closing_message")),
            targetAudience=cls._text(row.get("target_audience")),
            customerProfile=cls._text(row.get("customer_profile")),
            salesGoals=cls._rules(row.get("sales_goals")),
            qualificationRules=cls._rules(row.get("qualification_rules")),
            opportunityCriteria=cls._rules(row.get("opportunity_criteria")),
            objectionHandling=cls._object(row.get("objection_handling")),
            upsellRules=cls._rules(row.get("upsell_rules")),
            recommendationRules=cls._rules(row.get("recommendation_rules")),
            humanHandoffCriteria=cls._rules(row.get("human_handoff_criteria")),
            escalationRules=cls._rules(row.get("escalation_rules")),
            restrictions=cls._rules(row.get("restrictions")),
            examples=cls._examples(row.get("examples")),
            activatedAt=row.get("activated_at"),
            updatedAt=row.get("updated_at"),
        )

    def _workspace_exists(self, workspace_id: str) -> bool:
        return bool(self.workspace_repo.buscar_workspace(workspace_id))

    def get_active_runtime(self, workspace_id: str) -> ActivePersonaRuntime | None:
        started = perf_counter()
        try:
            if not self._workspace_exists(workspace_id):
                logger.info("persona_runtime workspace_id=%s result=workspace_missing duration_ms=%.2f", workspace_id, (perf_counter() - started) * 1000)
                raise HTTPException(status_code=404, detail="Workspace não encontrado.")

            rows = [
                row for row in self.persona_repo.listar_por_workspace(workspace_id)
                if str(row.get("workspace_id")) == str(workspace_id)
                and row.get("status") == "active"
            ]
            if len(rows) > 1:
                logger.error("persona_runtime workspace_id=%s result=active_persona_invalid duration_ms=%.2f", workspace_id, (perf_counter() - started) * 1000)
                raise HTTPException(status_code=409, detail="Mais de uma Persona ativa foi encontrada para este workspace.")
            if not rows:
                logger.info("persona_runtime workspace_id=%s result=active_persona_missing duration_ms=%.2f", workspace_id, (perf_counter() - started) * 1000)
                return None

            runtime = self._runtime(rows[0], workspace_id)
            logger.info("persona_runtime workspace_id=%s persona_id=%s version=%s result=active_persona_available duration_ms=%.2f", workspace_id, runtime.personaId, runtime.version, (perf_counter() - started) * 1000)
            return runtime
        except HTTPException:
            raise
        except Exception:
            logger.exception("persona_runtime workspace_id=%s result=active_persona_invalid duration_ms=%.2f", workspace_id, (perf_counter() - started) * 1000)
            raise HTTPException(status_code=503, detail="Não foi possível resolver a Persona ativa.")

    def require_active_runtime(self, workspace_id: str) -> ActivePersonaRuntime:
        runtime = self.get_active_runtime(workspace_id)
        if runtime is None:
            raise HTTPException(status_code=404, detail="Nenhuma Persona ativa foi encontrada para este workspace.")
        return runtime


persona_runtime_service = PersonaRuntimeService()
