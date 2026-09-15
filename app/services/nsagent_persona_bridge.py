"""Publica a persona ativa do ChatBô para o NSAgent (ai_agent_persona_versions)."""

from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any

from app.config.settings import (
    NSAGENT_PERSONA_KEY,
    NSAGENT_PERSONA_TENANT_ID,
)
from app.services.persona_restrictions import GROUP_LABELS, GROUP_ORDER, decode_restrictions
from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

_VOLATILE = (
    re.compile(r"R\$\s*\d", re.I),
    re.compile(r"\b(?:estoque|disponibilidade)\s*[:=]\s*\d+", re.I),
    re.compile(r"https?://[^\s]+(?:checkout|pagamento|cart|pedido)", re.I),
)


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _clean(value: Any) -> str:
    if value is None:
        return ""
    return str(value).strip()


def _list_lines(value: Any, *, bullet: str = "- ") -> str:
    if not isinstance(value, list) or not value:
        return ""
    lines: list[str] = []
    for item in value:
        if isinstance(item, str) and item.strip():
            lines.append(f"{bullet}{item.strip()}")
        elif isinstance(item, dict):
            # objection_handling style sometimes leaks into lists
            text = _clean(item.get("text") or item.get("rule") or item.get("label"))
            if text:
                lines.append(f"{bullet}{text}")
    return "\n".join(lines)


def _objection_block(value: Any) -> str:
    if not isinstance(value, dict) or not value:
        return ""
    lines: list[str] = []
    for key, raw in value.items():
        label = _clean(key)
        if isinstance(raw, str) and raw.strip():
            lines.append(f"- {label}: {raw.strip()}")
        elif isinstance(raw, dict):
            reply = _clean(raw.get("response") or raw.get("reply") or raw.get("text"))
            if reply:
                lines.append(f"- {label}: {reply}")
        elif isinstance(raw, list):
            nested = _list_lines(raw, bullet="  - ")
            if nested:
                lines.append(f"- {label}:\n{nested}")
    return "\n".join(lines)


def _examples_block(value: Any) -> str:
    if not isinstance(value, list) or not value:
        return ""
    chunks: list[str] = []
    for idx, item in enumerate(value, start=1):
        if not isinstance(item, dict):
            continue
        customer = _clean(item.get("customerMessage") or item.get("customer_message"))
        expected = _clean(item.get("expectedResponse") or item.get("expected_response"))
        if customer and expected:
            chunks.append(
                f"Exemplo {idx}:\nCliente: {customer}\nAgente: {expected}"
            )
    return "\n\n".join(chunks)


KNOWLEDGE_TOTAL_CAP = 24_000


def _knowledge_block(docs: list[dict] | None) -> str:
    if not docs:
        return ""
    chunks: list[str] = []
    used = 0
    for idx, doc in enumerate(docs, start=1):
        name = _clean(doc.get("filename") or doc.get("name")) or f"Documento {idx}"
        body = _clean(doc.get("extracted_text") or doc.get("text"))
        if not body:
            continue
        remaining = KNOWLEDGE_TOTAL_CAP - used
        if remaining <= 200:
            chunks.append("[… documentos adicionais omitidos por limite de tamanho …]")
            break
        if len(body) > remaining:
            body = body[:remaining] + "\n[… truncado …]"
        chunk = f"### {name}\n{body}"
        chunks.append(chunk)
        used += len(chunk)
    if not chunks:
        return ""
    return (
        "Base de conhecimento aprovada (use estes documentos como referência factual; "
        "não invente o que não estiver aqui nem em ferramentas):\n\n"
        + "\n\n".join(chunks)
    )


def compile_instructions(persona: dict, knowledge_docs: list[dict] | None = None) -> str:
    """Converte campos estruturados do ChatBô em instructions do NSAgent."""
    name = _clean(persona.get("name")) or "Agente comercial"
    role = _clean(persona.get("role")) or "assistente comercial"
    segment = _clean(persona.get("segment"))
    language = _clean(persona.get("language")) or "pt-BR"
    tone = _clean(persona.get("tone"))
    tone_details = _clean(persona.get("tone_details"))
    greeting = _clean(persona.get("greeting"))
    introduction = _clean(persona.get("introduction"))
    address = _clean(persona.get("customer_address_style"))
    closing = _clean(persona.get("closing_message"))
    audience = _clean(persona.get("target_audience"))
    profile = _clean(persona.get("customer_profile"))

    parts: list[str] = [
        f"Identidade configurada: {name}. Função: {role}. Idioma: {language}.",
        "Use apenas informações confiáveis do contexto/ferramentas. Não invente preço, estoque, prazo ou status de pedido.",
        "Quando faltar dado confiável, diga que precisa confirmar antes de responder.",
    ]
    if language and language.lower() not in {"pt-br", "pt_br", "pt"}:
        parts.append(f"Idioma preferencial configurado: {language}.")
    if segment:
        parts.append(f"Segmento de atuação: {segment}.")
    if tone:
        parts.append(f"Tom de voz: {tone}.")
    if tone_details:
        parts.append(f"Detalhes de tom: {tone_details}")
    if address:
        parts.append(f"Forma de se dirigir ao cliente: {address}.")
    if greeting:
        parts.append(f"Saudação padrão (adapte ao contexto): {greeting}")
    if introduction:
        parts.append(f"Apresentação: {introduction}")
    if closing:
        parts.append(f"Encerramento sugerido: {closing}")
    if audience:
        parts.append(f"Público-alvo: {audience}")
    if profile:
        parts.append(f"Perfil do cliente: {profile}")

    goals = _list_lines(persona.get("sales_goals"))
    if goals:
        parts.append("Objetivos comerciais:\n" + goals)

    qualification = _list_lines(persona.get("qualification_rules"))
    if qualification:
        parts.append("Regras de qualificação:\n" + qualification)

    opportunity = _list_lines(persona.get("opportunity_criteria"))
    if opportunity:
        parts.append("Critérios de oportunidade:\n" + opportunity)

    raw_objections = persona.get("objection_handling")
    objections = (
        _objection_block(raw_objections)
        if isinstance(raw_objections, dict)
        else _list_lines(raw_objections)
    )
    if objections:
        parts.append("Tratamento de objeções:\n" + objections)

    upsell = _list_lines(persona.get("upsell_rules"))
    if upsell:
        parts.append("Regras de upsell:\n" + upsell)

    recommend = _list_lines(persona.get("recommendation_rules"))
    if recommend:
        parts.append("Regras de recomendação:\n" + recommend)

    handoff = _list_lines(persona.get("human_handoff_criteria"))
    if handoff:
        parts.append("Quando transferir para humano:\n" + handoff)

    escalation = _list_lines(persona.get("escalation_rules"))
    if escalation:
        parts.append("Regras de escalonamento:\n" + escalation)

    restriction_groups = decode_restrictions(persona.get("restrictions"))
    grouped_restrictions = [
        f"{GROUP_LABELS[group]}:\n{_list_lines(restriction_groups[group])}"
        for group in GROUP_ORDER
        if restriction_groups[group]
    ]
    if grouped_restrictions:
        parts.extend(grouped_restrictions)
    else:
        restrictions = _list_lines(persona.get("restrictions"))
        if restrictions:
            parts.append("Restrições obrigatórias:\n" + restrictions)

    examples = _examples_block(persona.get("examples"))
    if examples:
        parts.append("Exemplos de diálogo (estilo, não copie literalmente se o contexto for outro):\n" + examples)

    knowledge = _knowledge_block(knowledge_docs)
    if knowledge:
        parts.append(knowledge)

    text = "\n\n".join(parts).strip()
    for pattern in _VOLATILE:
        text = pattern.sub("[dado dinâmico — consulte ferramentas]", text)
    return text


class NsAgentPersonaBridge:
    def __init__(
        self,
        *,
        tenant_id: str | None = None,
        persona_key: str | None = None,
    ) -> None:
        self.tenant_id = (tenant_id or NSAGENT_PERSONA_TENANT_ID or "newstore").strip()
        self.persona_key = (persona_key or NSAGENT_PERSONA_KEY or "newstore_commercial").strip()

    def _load_knowledge_docs(self, persona: dict) -> list[dict]:
        persona_id = str(persona.get("id") or "").strip()
        workspace_id = str(persona.get("workspace_id") or "").strip()
        if not persona_id or not workspace_id:
            return []
        try:
            from app.repositories.persona_attachment_repository import PersonaAttachmentRepository

            return PersonaAttachmentRepository().listar_processados(persona_id, workspace_id)
        except Exception as exc:
            logger.warning("Não foi possível carregar anexos da persona %s: %s", persona_id, exc)
            return []

    def publish_active(self, persona: dict, *, activated_by: str | None = None) -> dict:
        """Validate real identity before compiling, then publish atomically in Postgres."""
        from uuid import UUID
        from app.repositories.persona_repository import PersonaRepository

        try:
            persona_id = str(UUID(str(persona.get("id") or "")))
            workspace_id = str(UUID(str(persona.get("workspace_id") or "")))
        except ValueError as exc:
            raise ValueError("invalid_persona_workspace_link") from exc
        stored = PersonaRepository().buscar_por_id_workspace(persona_id, workspace_id)
        if not stored:
            raise ValueError("invalid_persona_workspace_link")
        expected = int(stored.get("version") or 1)
        # Legacy activation callers passed the upcoming version; compilation
        # always uses the locked, persisted profile, never arbitrary caller text.
        if int(persona.get("version") or 1) not in {expected, expected + 1}:
            raise ValueError("persona_version_conflict")
        knowledge_docs = self._load_knowledge_docs(stored)
        instructions = compile_instructions(stored, knowledge_docs)
        if len(instructions) < 40:
            raise ValueError("instructions_too_short")
        result = supabase.rpc("publish_nsagent_persona", {
            "p_workspace_id": workspace_id,
            "p_persona_id": persona_id,
            "p_expected_profile_version": expected,
            "p_tenant_id": self.tenant_id,
            "p_persona_key": self.persona_key,
            "p_instructions": instructions,
            "p_instructions_hash": _hash(instructions),
            "p_activated_by": activated_by,
            "p_knowledge_docs": len(knowledge_docs),
        }).execute().data
        if isinstance(result, list):
            result = result[0] if result else None
        if not isinstance(result, dict) or not result.get("published"):
            raise RuntimeError("persona_publish_failed")
        return {**result, "tenantId": self.tenant_id, "personaKey": self.persona_key,
                "instructionsChars": len(instructions)}

    def archive_active(self, *, workspace_id: str) -> dict:
        from uuid import UUID
        workspace_id = str(UUID(workspace_id))
        rows = (supabase.table("ai_agent_persona_versions")
                .update({"status": "archived", "archived_at": datetime.now(timezone.utc).isoformat()})
                .eq("tenant_id", self.tenant_id).eq("persona_key", self.persona_key)
                .eq("workspace_id", workspace_id).eq("status", "active").execute().data or [])
        return {"published": False, "archivedPrevious": len(rows),
                "tenantId": self.tenant_id, "personaKey": self.persona_key}

    def update_active(self, persona: dict, patch: dict, *, activated_by: str) -> dict:
        """Compile a proposed edit; profile, history and activation commit together."""
        from uuid import UUID
        workspace_id = str(UUID(str(persona["workspace_id"])))
        persona_id = str(UUID(str(persona["id"])))
        proposed = {**persona, **patch}
        docs = self._load_knowledge_docs(persona)
        instructions = compile_instructions(proposed, docs)
        result = supabase.rpc("update_and_publish_nsagent_persona", {
            "p_workspace_id": workspace_id, "p_persona_id": persona_id,
            "p_expected_profile_version": int(persona["version"]), "p_patch": patch,
            "p_tenant_id": self.tenant_id, "p_persona_key": self.persona_key,
            "p_instructions": instructions, "p_instructions_hash": _hash(instructions),
            "p_activated_by": activated_by, "p_knowledge_docs": len(docs),
        }).execute().data
        if isinstance(result, list):
            result = result[0] if result else None
        if not isinstance(result, dict) or not result.get("published"):
            raise RuntimeError("persona_publish_failed")
        return result


nsagent_persona_bridge = NsAgentPersonaBridge()
