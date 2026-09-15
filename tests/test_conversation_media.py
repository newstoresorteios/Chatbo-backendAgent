from unittest.mock import MagicMock, patch

import pytest
from fastapi import HTTPException

from app.providers.whatsapp_meta import WhatsAppMetaProvider
from app.services.conversation_media import signed_media_url, store_media, validate_media
from app.services.conversas_service import _map_mensagem
from app.services.whatsapp_service import WhatsAppService


def test_media_validation_rejects_unsupported_or_oversized_file():
    assert validate_media(b"file", "application/pdf") == "document"
    with pytest.raises(HTTPException):
        validate_media(b"file", "application/x-msdownload")
    with pytest.raises(HTTPException):
        validate_media(b"x" * (16 * 1024 * 1024 + 1), "image/png")


def test_private_media_upload_and_signed_url():
    with patch("app.services.conversation_media.supabase") as client:
        bucket = client.storage.from_.return_value
        bucket.create_signed_url.return_value = {"signedURL": "https://private/signed"}
        path = store_media("ws-1", "conv-1", "../../photo.png", b"image", "image/png")
        assert path.startswith("ws-1/conv-1/")
        assert path.endswith("-photo.png")
        bucket.upload.assert_called_once()
        assert signed_media_url(path) == "https://private/signed"
        bucket.create_signed_url.assert_called_once_with(path, 900)


def test_message_mapping_adds_signed_media_metadata():
    with patch("app.services.conversation_media.signed_media_url", return_value="https://signed"):
        result = _map_mensagem({
            "id": "msg", "conversa_id": "conv", "content": "foto",
            "media_type": "image", "media_filename": "photo.png",
            "media_storage_path": "ws/conv/photo.png", "media_byte_size": 123,
        })
    assert result["mediaUrl"] == "https://signed"
    assert result["mediaByteSize"] == 123


def test_meta_upload_then_send_media_id():
    provider = WhatsAppMetaProvider(access_token="test", phone_number_id="123")
    upload = MagicMock()
    upload.json.return_value = {"id": "media-id"}
    sent = MagicMock()
    sent.json.return_value = {"messages": [{"id": "message-id"}]}
    with patch("app.providers.whatsapp_meta.requests.post", side_effect=[upload, sent]) as post:
        media_id = provider.upload_media("photo.png", b"image", "image/png")
        response = provider.enviar_media("+55 11 9999", "image", media_id, "photo.png", "Legenda")
    assert response["messages"][0]["id"] == "message-id"
    assert post.call_args_list[0].kwargs["files"]["file"] == ("photo.png", b"image", "image/png")
    assert post.call_args_list[1].kwargs["json"]["image"] == {"id": "media-id", "caption": "Legenda"}


def test_whatsapp_inbound_media_caption_or_fallback():
    service = WhatsAppService()
    assert service._extrair_conteudo({"type": "image", "image": {"caption": "Produto"}}) == "Produto"
    assert service._extrair_conteudo({"type": "document", "document": {"filename": "quote.pdf"}}) == "[document: quote.pdf]"


def test_webhook_never_falls_back_to_other_workspace_channel():
    service = WhatsAppService()
    service.canais = MagicMock()
    service.canais.get_canal_by_phone_number_id.return_value = None
    assert service._resolve_canal("unknown-phone-id") is None
    service.canais.list_canais.assert_not_called()
