"""CRUD de anexos de conhecimento da persona."""

from __future__ import annotations

import logging

from fastapi import HTTPException, UploadFile

from app.repositories.persona_attachment_repository import PersonaAttachmentRepository
from app.repositories.persona_repository import PersonaRepository
from app.services.persona_storage import persona_storage
from app.services.persona_text_extract import (
    ALLOWED_CONTENT_TYPES,
    allowed_filename,
    extract_text,
)
from app.services.workspace_service import WORKSPACE_ADMIN_ROLES, workspace_service

logger = logging.getLogger(__name__)

PERSONA_VIEW_ROLES = {"owner", "admin", "supervisor"}
MAX_FILE_BYTES = 5 * 1024 * 1024
MAX_FILES_PER_PERSONA = 10


class PersonaAttachmentService:
    def __init__(
        self,
        attachment_repo: PersonaAttachmentRepository | None = None,
        persona_repo: PersonaRepository | None = None,
    ) -> None:
        self.attachments = attachment_repo or PersonaAttachmentRepository()
        self.personas = persona_repo or PersonaRepository()

    def _context(self, usuario: dict) -> dict:
        return workspace_service.get_current_workspace_context(usuario)

    def _require_view(self, context: dict) -> None:
        if context.get("workspaceRole") not in PERSONA_VIEW_ROLES:
            raise HTTPException(status_code=403, detail="Sem permissão para visualizar anexos da persona.")

    def _require_admin(self, context: dict) -> None:
        if context.get("workspaceRole") not in WORKSPACE_ADMIN_ROLES:
            raise HTTPException(status_code=403, detail="Sem permissão para alterar anexos da persona.")

    def _persona(self, context: dict, persona_id: str) -> dict:
        persona = self.personas.buscar_por_id_workspace(persona_id, context["workspaceId"])
        if not persona:
            raise HTTPException(status_code=404, detail="Persona não encontrada.")
        return persona

    def _response(self, row: dict) -> dict:
        return {
            "id": str(row.get("id")),
            "personaId": str(row.get("persona_id")),
            "workspaceId": str(row.get("workspace_id")),
            "filename": row.get("filename"),
            "contentType": row.get("content_type"),
            "byteSize": int(row.get("byte_size") or 0),
            "status": row.get("status"),
            "errorMessage": row.get("error_message"),
            "hasExtractedText": bool((row.get("extracted_text") or "").strip()),
            "extractedChars": len((row.get("extracted_text") or "").strip()),
            "createdAt": row.get("created_at"),
            "updatedAt": row.get("updated_at"),
        }

    def listar(self, usuario: dict, persona_id: str) -> dict:
        context = self._context(usuario)
        self._require_view(context)
        self._persona(context, persona_id)
        items = [
            self._response(row)
            for row in self.attachments.listar(persona_id, context["workspaceId"])
        ]
        return {"items": items, "total": len(items)}

    async def upload(self, usuario: dict, persona_id: str, file: UploadFile) -> dict:
        context = self._context(usuario)
        self._require_admin(context)
        persona = self._persona(context, persona_id)
        workspace_id = context["workspaceId"]

        filename = (file.filename or "arquivo").strip()
        if not allowed_filename(filename):
            raise HTTPException(
                status_code=400,
                detail="Tipo de arquivo não suportado. Use TXT, MD, CSV, JSON ou PDF.",
            )

        content_type = (file.content_type or "application/octet-stream").split(";")[0].strip().lower()
        if content_type and content_type not in ALLOWED_CONTENT_TYPES and not content_type.startswith("text/"):
            raise HTTPException(status_code=400, detail=f"Content-Type não permitido: {content_type}")

        count = self.attachments.contar(persona_id, workspace_id)
        if count >= MAX_FILES_PER_PERSONA:
            raise HTTPException(
                status_code=400,
                detail=f"Limite de {MAX_FILES_PER_PERSONA} anexos por persona.",
            )

        content = await file.read()
        if not content:
            raise HTTPException(status_code=400, detail="Arquivo vazio.")
        if len(content) > MAX_FILE_BYTES:
            raise HTTPException(status_code=400, detail="Arquivo maior que 5 MB.")

        try:
            extracted = extract_text(filename, content, content_type)
            status = "processed"
            error_message = None
        except Exception as exc:
            logger.warning("Falha ao extrair texto de %s: %s", filename, exc)
            extracted = None
            status = "failed"
            error_message = str(exc)

        try:
            storage_path = persona_storage.upload(
                workspace_id=workspace_id,
                persona_id=persona_id,
                filename=filename,
                content=content,
                content_type=content_type or "application/octet-stream",
            )
        except Exception as exc:
            logger.exception("Upload storage falhou: %s", exc)
            raise HTTPException(
                status_code=502,
                detail=f"Não foi possível salvar o arquivo no storage ({exc}).",
            ) from exc

        row = self.attachments.criar(
            {
                "persona_id": persona_id,
                "workspace_id": workspace_id,
                "filename": filename,
                "content_type": content_type,
                "byte_size": len(content),
                "storage_path": storage_path,
                "extracted_text": extracted,
                "status": status,
                "error_message": error_message,
                "created_by": str(usuario.get("id")) if usuario.get("id") else None,
            }
        )

        # Se a persona já está ativa, republica no NSAgent com o conhecimento novo.
        if persona.get("status") == "active" and status == "processed":
            try:
                from app.services.persona_service import persona_service

                persona_service._publish_to_nsagent(persona, user_id=str(usuario.get("id")))
            except Exception as exc:
                logger.warning("Republicação NSAgent após upload falhou: %s", exc)

        return self._response(row)

    def remover(self, usuario: dict, persona_id: str, attachment_id: str) -> dict:
        context = self._context(usuario)
        self._require_admin(context)
        persona = self._persona(context, persona_id)
        workspace_id = context["workspaceId"]
        row = self.attachments.buscar(attachment_id, persona_id, workspace_id)
        if not row:
            raise HTTPException(status_code=404, detail="Anexo não encontrado.")

        try:
            persona_storage.delete(str(row.get("storage_path") or ""))
        except Exception as exc:
            logger.warning("Falha ao remover do storage: %s", exc)

        self.attachments.remover(attachment_id, workspace_id)

        if persona.get("status") == "active":
            try:
                from app.services.persona_service import persona_service

                persona_service._publish_to_nsagent(persona, user_id=str(usuario.get("id")))
            except Exception as exc:
                logger.warning("Republicação NSAgent após delete falhou: %s", exc)

        return {"success": True, "id": attachment_id}


persona_attachment_service = PersonaAttachmentService()
