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
    if not url:
        return {"mediaType": kind} if meta.get("image_url_present") and kind in {"image", "video"} else {}
    if kind not in {"image", "video"}:
        kind = "image"
    if urlsplit(url).path.lower().endswith((".mp4", ".mov", ".m4v")):
        kind = "video"
    return {"mediaType": kind, "mediaUrl": url}


def enrich_ai_message_media(messages: list[dict], workspace_id: str | None) -> list[dict]:
    """One workspace-scoped lookup per page; no public raw payload or credentials."""
    if not workspace_id:
        return messages
    ids = {}
    for message in messages:
        external = str(message.get("externalId") or message.get("id") or "")
        match = re.fullmatch(r"ai-in-(\d+)", external)
        if match and not message.get("mediaUrl"):
            ids[match[1]] = True
    if not ids:
        return messages
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
