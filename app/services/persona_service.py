from datetime import datetime
from typing import Any, Callable

from fastapi import HTTPException

from app.repositories.persona_repository import PersonaRepository
from app.services.openai_provider import call_openai_resilient
from app.services.workspace_service import WORKSPACE_ADMIN_ROLES, workspace_service

PERSONA_VIEW_ROLES = {"owner", "admin", "supervisor"}
REQUIRED_ACTIVATION_FIELDS = {
    "name": "name",
    "role": "role",
    "segment": "segment",
    "language": "language",
    "tone": "tone",
    "greeting": "greeting",
    "targetAudience": "target_audience",
    "salesGoals": "sales_goals",
    "qualificationRules": "qualification_rules",
    "restrictions": "restrictions",
}
LIST_LIMIT = 30


class PersonaService:
    def __init__(self, repo: PersonaRepository | None = None, ai_generator: Callable[[str, str], str | None] | None = None):
        self.repo = repo or PersonaRepository()
        self.ai_generator = ai_generator or self._generate_isolated_text

    def _context(self, usuario: dict) -> dict:
        return workspace_service.get_current_workspace_context(usuario)

    def _require_view(self, context: dict) -> None:
        if context.get("workspaceRole") not in PERSONA_VIEW_ROLES:
            raise HTTPException(status_code=403, detail="Você não possui permissão para visualizar personas")

    def _require_admin(self, context: dict, message: str) -> None:
        if context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail=message)

    def _clean_text(self, value: Any) -> str | None:
        if value is None:
            return None
        text = str(value).strip()
        return text or None

    def _clean_list(self, value: Any) -> list:
        if not isinstance(value, list):
            return []
        cleaned = []
        for item in value[:LIST_LIMIT]:
            if isinstance(item, str):
                text = item.strip()
                if text:
                    cleaned.append(text)
            elif isinstance(item, dict):
                cleaned.append(item)
        return cleaned

    def _examples_payload(self, examples: Any) -> list[dict]:
        result = []
        for item in self._clean_list(examples):
            if not isinstance(item, dict):
                continue
            customer_message = self._clean_text(item.get("customerMessage") or item.get("customer_message"))
            expected_response = self._clean_text(item.get("expectedResponse") or item.get("expected_response"))
            if customer_message and expected_response:
                result.append({
                    "customerMessage": customer_message,
                    "expectedResponse": expected_response,
                })
        return result

    def _editable_to_db(self, payload: dict, *, partial: bool = False) -> dict:
        mapping = {
            "name": "name",
            "role": "role",
            "segment": "segment",
            "language": "language",
            "tone": "tone",
            "toneDetails": "tone_details",
            "greeting": "greeting",
            "introduction": "introduction",
            "customerAddressStyle": "customer_address_style",
            "closingMessage": "closing_message",
            "targetAudience": "target_audience",
            "customerProfile": "customer_profile",
        }
        list_mapping = {
            "salesGoals": "sales_goals",
            "qualificationRules": "qualification_rules",
            "opportunityCriteria": "opportunity_criteria",
            "humanHandoffCriteria": "human_handoff_criteria",
            "upsellRules": "upsell_rules",
            "recommendationRules": "recommendation_rules",
            "escalationRules": "escalation_rules",
            "restrictions": "restrictions",
        }
        db: dict = {}
        for src, dest in mapping.items():
            if src in payload:
                db[dest] = self._clean_text(payload.get(src))
            elif not partial and src == "language":
                db[dest] = "pt-BR"
        for src, dest in list_mapping.items():
            if src in payload:
                db[dest] = self._clean_list(payload.get(src))
            elif not partial:
                db[dest] = []
        if "objectionHandling" in payload:
            db["objection_handling"] = payload.get("objectionHandling") if isinstance(payload.get("objectionHandling"), dict) else {}
        elif not partial:
            db["objection_handling"] = {}
        if "examples" in payload:
            db["examples"] = self._examples_payload(payload.get("examples"))
        elif not partial:
            db["examples"] = []
        return db

    def _response(self, row: dict) -> dict:
        return {
            "id": str(row.get("id")),
            "workspaceId": str(row.get("workspace_id")),
            "name": row.get("name"),
            "role": row.get("role"),
            "segment": row.get("segment"),
            "language": row.get("language"),
            "tone": row.get("tone"),
            "toneDetails": row.get("tone_details"),
            "greeting": row.get("greeting"),
            "introduction": row.get("introduction"),
            "customerAddressStyle": row.get("customer_address_style"),
            "closingMessage": row.get("closing_message"),
            "targetAudience": row.get("target_audience"),
            "customerProfile": row.get("customer_profile"),
            "salesGoals": row.get("sales_goals") or [],
            "qualificationRules": row.get("qualification_rules") or [],
            "opportunityCriteria": row.get("opportunity_criteria") or [],
            "humanHandoffCriteria": row.get("human_handoff_criteria") or [],
            "objectionHandling": row.get("objection_handling") or {},
            "upsellRules": row.get("upsell_rules") or [],
            "recommendationRules": row.get("recommendation_rules") or [],
            "escalationRules": row.get("escalation_rules") or [],
            "restrictions": row.get("restrictions") or [],
            "examples": row.get("examples") or [],
            "status": row.get("status") or "draft",
            "version": int(row.get("version") or 1),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
            "activatedAt": row.get("activated_at"),
            "deactivatedAt": row.get("deactivated_at"),
        }

    def _version_response(self, row: dict) -> dict:
        return {
            "id": str(row.get("id")),
            "personaId": str(row.get("persona_id")),
            "version": int(row.get("version") or 1),
            "snapshot": row.get("snapshot") or {},
            "changeType": row.get("change_type"),
            "createdBy": row.get("created_by"),
            "createdAt": row.get("created_at"),
        }

    def _snapshot(self, persona: dict, change_type: str, user_id: str) -> None:
        self.repo.criar_versao({
            "persona_id": persona.get("id"),
            "workspace_id": persona.get("workspace_id"),
            "version": int(persona.get("version") or 1),
            "snapshot": self._response(persona),
            "change_type": change_type,
            "created_by": user_id,
        })

    def listar(self, usuario: dict) -> dict:
        context = self._context(usuario)
        self._require_view(context)
        rows = self.repo.listar_por_workspace(context["workspaceId"])
        items = [self._response(row) for row in rows]
        active = next((item["id"] for item in items if item.get("status") == "active"), None)
        return {"items": items, "total": len(items), "activePersonaId": active}

    def criar(self, usuario: dict, payload: dict) -> dict:
        context = self._context(usuario)
        self._require_admin(context, "Você não possui permissão para criar personas.")
        db_payload = self._editable_to_db(payload)
        now = datetime.utcnow().isoformat()
        persona = self.repo.criar({
            **db_payload,
            "workspace_id": context["workspaceId"],
            "status": "draft",
            "version": 1,
            "created_by": str(usuario.get("id")),
            "updated_by": str(usuario.get("id")),
            "created_at": now,
            "updated_at": now,
        })
        self._snapshot(persona, "created", str(usuario.get("id")))
        return self._response(persona)

    def obter(self, usuario: dict, persona_id: str) -> dict:
        context = self._context(usuario)
        self._require_view(context)
        persona = self.repo.buscar_por_id_workspace(persona_id, context["workspaceId"])
        if not persona:
            raise HTTPException(status_code=404, detail="Persona não encontrada.")
        return self._response(persona)

    def atualizar(self, usuario: dict, persona_id: str, payload: dict) -> dict:
        context = self._context(usuario)
        self._require_admin(context, "Você não possui permissão para alterar esta persona.")
        persona = self.repo.buscar_por_id_workspace(persona_id, context["workspaceId"])
        if not persona:
            raise HTTPException(status_code=404, detail="Persona não encontrada.")
        db_payload = self._editable_to_db(payload, partial=True)
        if not db_payload:
            return self._response(persona)
        updated = self.repo.atualizar(persona_id, context["workspaceId"], {
            **db_payload,
            "version": int(persona.get("version") or 1) + 1,
            "updated_by": str(usuario.get("id")),
        })
        self._snapshot(updated, "updated", str(usuario.get("id")))
        return self._response(updated)

    def _missing_activation_fields(self, persona: dict) -> list[str]:
        missing = []
        for public_name, db_name in REQUIRED_ACTIVATION_FIELDS.items():
            value = persona.get(db_name)
            if isinstance(value, list):
                if not value:
                    missing.append(public_name)
            elif not self._clean_text(value):
                missing.append(public_name)
        return missing

    def ativar(self, usuario: dict, persona_id: str) -> dict:
        context = self._context(usuario)
        self._require_admin(context, "Você não possui permissão para alterar esta persona.")
        persona = self.repo.buscar_por_id_workspace(persona_id, context["workspaceId"])
        if not persona:
            raise HTTPException(status_code=404, detail="Persona não encontrada.")
        if persona.get("status") == "active":
            return self._response(persona)
        missing = self._missing_activation_fields(persona)
        if missing:
            raise HTTPException(
                status_code=400,
                detail={"message": "A persona ainda não pode ser ativada.", "missingFields": missing},
            )

        user_id = str(usuario.get("id"))
        current_active = self.repo.buscar_ativa(context["workspaceId"])
        if current_active and current_active.get("id") != persona_id:
            deactivated = self.repo.atualizar(str(current_active.get("id")), context["workspaceId"], {
                "status": "inactive",
                "version": int(current_active.get("version") or 1) + 1,
                "updated_by": user_id,
                "deactivated_at": datetime.utcnow().isoformat(),
            })
            self._snapshot(deactivated, "deactivated", user_id)

        activated = self.repo.atualizar(persona_id, context["workspaceId"], {
            "status": "active",
            "version": int(persona.get("version") or 1) + 1,
            "updated_by": user_id,
            "activated_by": user_id,
            "activated_at": datetime.utcnow().isoformat(),
            "deactivated_at": None,
        })
        self._snapshot(activated, "activated", user_id)
        return self._response(activated)

    def desativar(self, usuario: dict, persona_id: str) -> dict:
        context = self._context(usuario)
        self._require_admin(context, "Você não possui permissão para alterar esta persona.")
        persona = self.repo.buscar_por_id_workspace(persona_id, context["workspaceId"])
        if not persona:
            raise HTTPException(status_code=404, detail="Persona não encontrada.")
        if persona.get("status") != "active":
            return self._response(persona)
        user_id = str(usuario.get("id"))
        updated = self.repo.atualizar(persona_id, context["workspaceId"], {
            "status": "inactive",
            "version": int(persona.get("version") or 1) + 1,
            "updated_by": user_id,
            "deactivated_at": datetime.utcnow().isoformat(),
        })
        self._snapshot(updated, "deactivated", user_id)
        return self._response(updated)

    def listar_versoes(self, usuario: dict, persona_id: str) -> list[dict]:
        context = self._context(usuario)
        self._require_view(context)
        if not self.repo.buscar_por_id_workspace(persona_id, context["workspaceId"]):
            raise HTTPException(status_code=404, detail="Persona não encontrada.")
        return [self._version_response(row) for row in self.repo.listar_versoes(persona_id, context["workspaceId"])]

    def obter_versao(self, usuario: dict, persona_id: str, version: int) -> dict:
        context = self._context(usuario)
        self._require_view(context)
        if not self.repo.buscar_por_id_workspace(persona_id, context["workspaceId"]):
            raise HTTPException(status_code=404, detail="Persona não encontrada.")
        row = self.repo.buscar_versao(persona_id, context["workspaceId"], version)
        if not row:
            raise HTTPException(status_code=404, detail="Versão não encontrada.")
        return self._version_response(row)

    def build_persona_test_prompt(self, persona_payload: dict, customer_message: str) -> str:
        persona = self._editable_to_db(persona_payload)
        return (
            "Teste temporario de persona comercial do NITRUS. Esta resposta e apenas uma demonstracao.\n"
            "Nao salve dados, nao execute acoes, nao prometa preco, estoque, prazo ou integracao externa.\n"
            "Quando faltar informacao confiavel, diga que precisa confirmar antes de responder.\n\n"
            f"Nome/persona: {persona.get('name') or 'Nao configurado'}\n"
            f"Funcao: {persona.get('role') or 'Nao configurado'}\n"
            f"Segmento: {persona.get('segment') or 'Nao configurado'}\n"
            f"Idioma: {persona.get('language') or 'pt-BR'}\n"
            f"Tom: {persona.get('tone') or 'Nao configurado'}\n"
            f"Detalhes do tom: {persona.get('tone_details') or 'Nao configurado'}\n"
            f"Saudacao: {persona.get('greeting') or 'Nao configurado'}\n"
            f"Publico-alvo: {persona.get('target_audience') or 'Nao configurado'}\n"
            f"Objetivos: {persona.get('sales_goals') or []}\n"
            f"Qualificacao: {persona.get('qualification_rules') or []}\n"
            f"Objecoes: {persona.get('objection_handling') or dict()}\n"
            f"Upsell: {persona.get('upsell_rules') or []}\n"
            f"Transferencia humana: {persona.get('escalation_rules') or persona.get('human_handoff_criteria') or []}\n"
            f"Restricoes: {persona.get('restrictions') or []}\n"
            f"Exemplos: {persona.get('examples') or []}\n\n"
            f"Mensagem simulada do cliente: {customer_message.strip()}"
        )

    def _generate_isolated_text(self, customer_message: str, prompt: str) -> str | None:
        return call_openai_resilient(customer_message, prompt, [], "agent")

    def testar(self, usuario: dict, payload: dict) -> dict:
        context = self._context(usuario)
        self._require_view(context)
        customer_message = self._clean_text(payload.get("customerMessage"))
        if not customer_message:
            raise HTTPException(status_code=400, detail="Mensagem do cliente é obrigatória.")
        prompt = self.build_persona_test_prompt(payload.get("persona") or {}, customer_message)
        try:
            response = self.ai_generator(customer_message, prompt)
        except Exception as exc:
            raise HTTPException(status_code=503, detail="O serviço de IA está temporariamente indisponível.") from exc
        if not response:
            raise HTTPException(status_code=503, detail="O serviço de IA está temporariamente indisponível.")
        return {
            "response": response,
            "warnings": [],
            "generatedAt": datetime.utcnow().isoformat(),
            "persisted": False,
            "activated": False,
        }


persona_service = PersonaService()
