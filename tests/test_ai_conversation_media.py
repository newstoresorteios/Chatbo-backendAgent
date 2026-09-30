from unittest.mock import MagicMock, patch

from app.services.ai_conversation_media import enrich_ai_message_media, inbound_media_fields


def test_jota_existing_message_receives_story_image_with_caption_preserved():
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.in_.return_value
    url = "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=123&signature=test"
    query.execute.return_value.data = [{"id": 1031, "channel_metadata": {
        "image_url": url, "image_url_present": True, "attachment_type": "image"}}]
    original = {"id": "uuid", "externalId": "ai-in-1031", "content": "Qual valor?"}
    with patch("app.services.ai_conversation_media.supabase", client):
        result = enrich_ai_message_media([original], "workspace-a")
    assert result[0]["mediaUrl"] == url
    assert result[0]["mediaType"] == "image"
    assert result[0]["content"] == "Qual valor?"
    assert "mediaUrl" not in original


def test_acknowledged_outbound_photo_is_shown_in_workspace_scoped_central():
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value
    photo = "https://images.tcdn.com.br/img/product.jpg"
    query.execute.return_value.data = [{"id": 1023, "provider_response": {"media_messages": [
        {"type": "image", "url": photo, "message_id": "meta-ack"}]}}]
    message = {"id": "central-id", "externalId": "ai-out-1023", "content": "Uma possibilidade"}
    with patch("app.services.ai_conversation_media.supabase", client):
        result = enrich_ai_message_media([message], "workspace-a")
    assert result[0]["mediaUrl"] == photo
    assert result[0]["content"] == message["content"]
    client.table.return_value.select.return_value.eq.assert_called_once_with("workspace_id", "workspace-a")
    client.table.return_value.select.return_value.eq.return_value.eq.assert_called_once_with("provider_send_ok", True)


def test_unsent_or_untrusted_outbound_photo_is_not_shown():
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value
    query.execute.return_value.data = [{"id": 1023, "provider_response": {"media_messages": [
        {"type": "image", "url": "https://images.tcdn.com.br/unsent.jpg"},
        {"type": "image", "url": "https://tcdn.com.br.evil.test/a.jpg", "message_id": "id"}]}}]
    message = {"id": "central-id", "externalId": "ai-out-1023", "content": "Uma possibilidade"}
    with patch("app.services.ai_conversation_media.supabase", client):
        assert enrich_ai_message_media([message], "workspace-a") == [message]
    client.table.return_value.select.return_value.eq.assert_called_once_with("workspace_id", "workspace-a")


def test_multiple_sent_photos_keep_unique_ids_and_do_not_repeat_text_or_photos():
    client = MagicMock()
    query = client.table.return_value.select.return_value.eq.return_value.eq.return_value.in_.return_value
    photos = [f"https://images.tcdn.com.br/{index}.jpg" for index in range(3)]
    query.execute.return_value.data = [{"id": 1023, "provider_response": {"media_messages": [
        {"type": "image", "url": url, "message_id": f"ack-{index}"} for index, url in enumerate(photos)]}}]
    original = {"id": "central-id", "externalId": "ai-out-1023", "content": "Três opções"}
    with patch("app.services.ai_conversation_media.supabase", client):
        result = enrich_ai_message_media([original], "workspace-a")
        assert enrich_ai_message_media(result, "workspace-a") == result
    assert [message["mediaUrl"] for message in result] == photos
    assert len({message["id"] for message in result}) == 3
    assert [message["content"] for message in result] == [original["content"], "", ""]
    assert "mediaUrl" not in original


def test_no_workspace_no_lookup_and_no_replacement_of_stored_media():
    message = {"externalId": "ai-in-1031", "mediaUrl": "https://storage/signed"}
    with patch("app.services.ai_conversation_media.supabase") as client:
        assert enrich_ai_message_media([message], None) == [message]
        assert enrich_ai_message_media([message], "workspace-a") == [message]
        client.table.assert_not_called()


def test_unknown_hosts_and_html_posts_are_not_embedded_as_media():
    for url in ["https://fbsbx.com.evil.test/a.jpg", "javascript:alert(1)",
                "https://instagram.com/p/ABC/", "http://lookaside.fbsbx.com/a.jpg"]:
        assert "mediaUrl" not in inbound_media_fields({"channel_metadata": {"image_url": url}})


def test_video_metadata_for_player():
    result = inbound_media_fields({"channel_metadata": {
        "image_url": "https://scontent.cdninstagram.com/story.mp4?signed=yes", "attachment_type": "image"}})
    assert result["mediaType"] == "video"


def test_sniffed_video_mime_survives_private_storage_failure():
    result = inbound_media_fields({'channel_metadata': {
        'image_url': 'https://lookaside.fbsbx.com/opaque?signature=secret',
        'attachment_type': 'image', 'media_content_type': 'video/mp4',
        'media_archive_error': 'storage_upload_http_403'}})
    assert result['mediaType'] == 'video'
    assert result['mediaContentType'] == 'video/mp4'
    assert result['mediaUrl'].startswith('https://lookaside.fbsbx.com/')


def test_private_archive_replaces_expired_meta_url_with_fresh_signed_video():
    metadata = {'image_url': 'https://lookaside.fbsbx.com/expired',
                'attachment_type': 'image', 'media_content_type': 'video/mp4',
                'media_storage_path': 'supabase://conversation-media/private/instagram-stories/workspace-a/' + 'a' * 48}
    with patch('app.services.ai_conversation_media.supabase') as db:
        db.storage.from_.return_value.create_signed_url.return_value = {'signedURL': 'https://storage/signed-new'}
        result = inbound_media_fields({'channel_metadata': metadata}, 'workspace-a')
        db.storage.from_.assert_called_once_with('conversation-media')
        db.storage.from_.return_value.create_signed_url.assert_called_once_with(
            'private/instagram-stories/workspace-a/' + 'a' * 48, 900)
    assert result == {'mediaUrl': 'https://storage/signed-new', 'mediaType': 'video', 'mediaContentType': 'video/mp4'}


def test_foreign_workspace_and_arbitrary_storage_paths_are_never_signed():
    for path in ['supabase://conversation-media/private/instagram-stories/other/' + 'a' * 48,
                 'supabase://persona-knowledge/private/instagram-stories/workspace-a/' + 'a' * 48,
                 'supabase://conversation-media/private/instagram-stories/workspace-a/../../secret']:
        with patch('app.services.ai_conversation_media.supabase') as db:
            assert not inbound_media_fields({'channel_metadata': {'media_storage_path': path}}, 'workspace-a')
            db.storage.from_.assert_not_called()


def test_storage_outage_falls_back_to_original_media():
    metadata = {'image_url': 'https://lookaside.fbsbx.com/still-valid', 'attachment_type': 'image',
                'media_storage_path': 'supabase://conversation-media/private/instagram-stories/workspace-a/' + 'a' * 48}
    with patch('app.services.ai_conversation_media.supabase') as db:
        db.storage.from_.return_value.create_signed_url.side_effect = RuntimeError('unavailable')
        result = inbound_media_fields({'channel_metadata': metadata}, 'workspace-a')
    assert result['mediaUrl'] == metadata['image_url']


def test_jota_opaque_video_uses_downloaded_mime_scoped_to_receiving_account():
    client = MagicMock()
    inbound = MagicMock()
    stories = MagicMock()
    client.table.side_effect = lambda name: inbound if name == "ai_inbound_messages" else stories
    inbound.select.return_value.eq.return_value.in_.return_value.execute.return_value.data = [{
        "id": 1031, "story_id": "story", "account_id": "our-account",
        "channel_metadata": {"image_url": "https://lookaside.fbsbx.com/ig_messaging_cdn/?asset_id=1",
                             "attachment_type": "image"},
    }]
    stories.select.return_value.eq.return_value.in_.return_value.in_.return_value.execute.return_value.data = [
        {"story_media_id": "story", "instagram_account_id": "other-account", "media_mime": "image/jpeg"},
        {"story_media_id": "story", "instagram_account_id": "our-account", "media_mime": "video/mp4"},
    ]
    with patch("app.services.ai_conversation_media.supabase", client):
        result = enrich_ai_message_media([{"externalId": "ai-in-1031"}], "workspace-a")
    assert result[0]["mediaType"] == "video"
    assert result[0]["mediaContentType"] == "video/mp4"
