from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import Mock
import pytest
from fastapi import HTTPException
from app.services.persona_attachment_service import PersonaAttachmentService


@pytest.mark.parametrize("found,updated,status", [(False,False,404),(True,False,409)])
def test_validity_edit_checks_workspace_and_concurrent_change(found,updated,status):
    attachments=SimpleNamespace(buscar=Mock(return_value={"id":"d"} if found else None),
                                atualizar_validade=Mock(return_value=None))
    personas=SimpleNamespace(buscar_por_id_workspace=Mock(return_value={"id":"p"}))
    service=PersonaAttachmentService(attachments,personas)
    service._context=lambda _: {"workspaceId":"w", "workspaceRole":"owner"}
    with pytest.raises(HTTPException) as error:
        service.atualizar_validade({},"p","d",valid_until=None,expected_updated_at=datetime.now(timezone.utc))
    assert error.value.status_code==status
    attachments.buscar.assert_called_once_with("d","p","w")
    if not found: attachments.atualizar_validade.assert_not_called()
