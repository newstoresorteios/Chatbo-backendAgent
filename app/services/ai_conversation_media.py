"""Expose received AI media to the authorized inbox, including existing history."""

import logging
import re
from urllib.parse import urlsplit

from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)


def _media_url(value) -> str | None:
    if not isinstance(value, str):
        return None
    try:
        parsed = urlsplit(value)
        host = (parsed.hostname or "").lower()
        if parsed.scheme == "https" and not parsed.username and not parsed.password and any(
            host == suffix or host.endswith("." + suffix)
            for suffix in ("fbsbx.com", "fbcdn.net", "cdninstagram.com")
        ):
            return value
    except ValueError:
        pass
    return None


def inbound_media_fields(row: dict, workspace_id: str | None = None) -> dict:
    meta = row.get("channel_metadata") or {}
    if not isinstance(meta, dict):
        return {}
    stored = meta.get('media_storage_path')
    if workspace_id and isinstance(stored, str):
        # Only sign paths owned by this authorized inbound's workspace, never a
        # caller-provided arbitrary bucket/object or a different tenant's path.
        prefix = f'supabase://conversation-media/private/instagram-stories/{workspace_id}/'
        if stored.startswith(prefix) and re.fullmatch(r'[a-f0-9]{48}', stored[len(prefix):]):
            try:
                path = stored.removeprefix('supabase://conversation-media/')
                result = supabase.storage.from_('conversation-media').create_signed_url(path, 900)
                signed = result.get('signedURL') or result.get('signedUrl')
                mime = str(meta.get('media_content_type') or '')
                if signed and mime.startswith(('image/', 'video/')):
                    return {'mediaUrl': signed, 'mediaType': mime.split('/', 1)[0], 'mediaContentType': mime}
            except Exception as exc:
                logger.warning('Archived AI media unavailable (%s)', type(exc).__name__)
    url = _media_url(meta.get("image_url"))
    kind = str(meta.get("attachment_type") or "").lower()
    mime = str(meta.get("media_content_type") or "")
    if mime.startswith(("image/", "video/")):
        kind = mime.split("/", 1)[0]
    if not url:
        return {"mediaType": kind} if meta.get("image_url_present") and kind in {"image", "video"} else {}
    if kind not in {"image", "video"}:
        kind = "image"
    if urlsplit(url).path.lower().endswith((".mp4", ".mov", ".m4v")):
        kind = "video"
    fields = {"mediaType": kind, "mediaUrl": url}
    if mime.startswith(("image/", "video/")):
        fields["mediaContentType"] = mime
    return fields


def enrich_ai_message_media(messages: list[dict], workspace_id: str | None) -> list[dict]:
    """One workspace-scoped lookup per page; no public raw payload or credentials."""
    if not workspace_id:
        return messages
    messages = enrich_ai_outbound_media(messages, workspace_id)
    ids = {}
    for message in messages:
        external = str(message.get("externalId") or message.get("id") or "")
        match = re.fullmatch(r"ai-in-(\d+)", external)
        if match and not message.get("mediaUrl"):
            ids[match[1]] = True
    if not ids:
        return messages
    return _enrich_ai_inbound_media(messages, workspace_id, ids)


def enrich_ai_outbound_media(messages: list[dict], workspace_id: str) -> list[dict]:
    """Show only catalog photos acknowledged by Meta, never merely planned ones."""
    ids = []
    for message in messages:
        match = re.fullmatch(r"ai-out-(\d+)", str(message.get("externalId") or message.get("id") or ""))
        if match:
            ids.append(match[1])
    if not ids:
        return messages
    try:
        rows = (supabase.table("ai_agent_responses").select("id,provider_response")
                .eq("workspace_id", workspace_id).eq("provider_send_ok", True)
                .in_("id", ids).execute().data or [])
        images = {}
        for row in rows:
            provider = row.get("provider_response") or {}
            if not isinstance(provider, dict):
                continue
            photos = []
            for receipt in provider.get("media_messages") or []:
                if not isinstance(receipt, dict) or receipt.get("type") != "image" or not receipt.get("message_id"):
                    continue
                url = receipt.get("url")
                try:
                    parsed = urlsplit(url) if isinstance(url, str) else None
                    host = (parsed.hostname or "").lower() if parsed else ""
                    if (parsed and parsed.scheme == "https" and not parsed.username and not parsed.password
                            and parsed.port in (None, 443)
                            and (host == "tcdn.com.br" or host.endswith(".tcdn.com.br")) and url not in photos):
                        photos.append(url)
                except ValueError:
                    continue
            images[f"ai-out-{row['id']}"] = photos[:3]
        enriched = []
        existing_ids = {str(message.get("id")) for message in messages}
        for message in messages:
            photos = images.get(str(message.get("externalId") or message.get("id")), [])
            if not photos:
                enriched.append(message)
                continue
            enriched.append({**message, "mediaType": "image", "mediaUrl": photos[0]})
            for index, url in enumerate(photos[1:], start=1):
                identity = message.get("id") or message.get("externalId")
                image_id = f"{identity}:image:{index}"
                if image_id in existing_ids:
                    continue
                enriched.append({**message, "id": image_id,
                                 "externalId": f"{message.get('externalId') or identity}:image:{index}",
                                 "content": "", "mediaType": "image", "mediaUrl": url})
        return enriched
    except Exception as exc:
        logger.warning("AI outbound media lookup unavailable (%s)", type(exc).__name__)
        return messages


def _enrich_ai_inbound_media(messages: list[dict], workspace_id: str, ids: dict) -> list[dict]:
    try:
        rows = (supabase.table("ai_inbound_messages").select(
                    "id,channel_metadata,story_id:raw->meta_event->message->reply_to->story->>id,"
                    "account_id:raw->meta_event->recipient->>id")
                .eq("workspace_id", workspace_id).in_("id", list(ids)).execute().data or [])
        media = {f"ai-in-{row['id']}": inbound_media_fields(row, workspace_id) for row in rows}
        # The receiver's account and story IDs came from workspace-scoped inbound
        # rows. The downloaded MIME fixes old opaque URLs mislabeled as images.
        story_rows = [row for row in rows if row.get("story_id") and row.get("account_id")]
        if story_rows:
            try:
                stories = (supabase.table("instagram_story_products")
                    .select("story_media_id,instagram_account_id,media_mime")
                    .eq("provider", "meta")
                    .in_("story_media_id", list({row["story_id"] for row in story_rows}))
                    .in_("instagram_account_id", list({row["account_id"] for row in story_rows}))
                    .execute().data or [])
                mimes = {(row["instagram_account_id"], row["story_media_id"]): row.get("media_mime")
                         for row in stories}
                for row in story_rows:
                    if media[f"ai-in-{row['id']}"].get('mediaContentType'):
                        continue  # The actual archived bytes take precedence.
                    mime = mimes.get((row["account_id"], row["story_id"])) or ""
                    if mime.startswith(("video/", "image/")):
                        media[f"ai-in-{row['id']}"].update(mediaType=mime.split("/", 1)[0], mediaContentType=mime)
            except Exception as exc:
                logger.warning("Story media type lookup unavailable (%s)", type(exc).__name__)
        return [{**message, **media.get(str(message.get("externalId") or message.get("id")), {})}
                if not message.get("mediaUrl") else message for message in messages]
    except Exception as exc:
        logger.warning("AI inbox media lookup unavailable (%s)", type(exc).__name__)
        return messages
