# YCloud Pilot Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Integrate one YCloud WhatsApp pilot number into the existing ChatBô channel and inbox flows, with bot and human handoff.

**Architecture:** Dedicated YCloud provider, service and router; existing Supabase conversations and React inbox remain the read model. Provider routing is determined by the conversation's channel record. A migration adds the customer-window timestamp and targeted constraints.

**Tech Stack:** FastAPI, Python, Supabase/Postgres, React 19, TypeScript, Vite.

**Spec:** `docs/superpowers/specs/2026-10-23-ycloud-pilot-design.md`

## Global Constraints

- Use server environment variables for YCloud API key and webhook secret.
- Pilot channel only; no automatic activation of the principal number.
- Preserve Meta, Brevo and XNamai credentials and routing.
- Keep YCloud messages scoped by workspace and channel.
- No live activation without YCloud registration, HTTPS webhook and credentials.

## Review Focus

- Duplicate webhook after a partial retry must not increase unread count or trigger a second bot reply.
- An old inbound event must not reopen the 24-hour window.
- A customer shared by two WhatsApp numbers must have distinct histories.
- Human takeover during a pending bot turn must prevent that bot's send.
- Generic channel update/toggle must not activate unvalidated YCloud credentials.

---

### Task 1: Provider, registration and signed webhook

**Files:** Create `app/providers/whatsapp_ycloud.py`, `app/services/ycloud_service.py`, `app/routes/ycloud.py`; modify `main.py`, `app/config/settings.py`, `app/repositories/platform_repository.py`, `app/services/platform_service.py`, `app/routes/platform.py`, `.env.example`; test `tests/test_ycloud_channel.py`.

**Interfaces:** `YCloudProvider.validate_number() -> dict`, `verify_signature(body: bytes, header: str, secret: str, now: int) -> bool`, `YCloudService.connect(workspace_id: str, name: str) -> dict`, `YCloudService.process_event(event: dict) -> dict`.

- [ ] Write provider tests for valid/invalid signature, stale timestamp, exact phone/WABA/ID and `CONNECTED` state; run them and confirm failures.
- [ ] Implement provider with `X-API-Key` and the documented YCloud endpoints; rerun tests.
- [ ] Write route tests for permissions, connection validation and invalid webhook signatures; confirm failures.
- [ ] Implement scoped registration and router; rerun tests.

### Task 2: Inbound persistence and status correlation

**Files:** Create `supabase/migrations/*_ycloud_channel_handoff.sql`; modify `app/repositories/conversa_repository.py`, `app/repositories/mensagem_repository.py`, `app/services/ycloud_service.py`, `app/services/ai_conversas_bridge.py`, `app/services/contact_inbox_service.py`, `app/services/platform_service.py`; test `tests/test_ycloud_channel.py`.

**Interfaces:** `YCloudService.ingest_inbound(payload: dict) -> bool`, `YCloudService.update_status(payload: dict) -> bool`; persisted `last_customer_message_at` and `ycloud:<provider-id>` external IDs.

- [ ] Write tests for a new conversation, duplicate message, same contact on another channel, old event timestamp, and status update; confirm failures.
- [ ] Add the migration with targeted unique constraints and inbox handoff state, then implement inbound and status persistence; rerun tests.
- [ ] Run existing inbox and provider-routing regression tests. Record baseline dependency failures separately.

### Task 3: Panel and real-time visibility

**Files:** Create `frontend/src/services/ycloud.service.ts` (in the frontend repository); modify `frontend/src/pages/ChannelsPage.tsx`, `frontend/src/pages/ConversationsPage.tsx`, `frontend/src/services/conversations.service.ts`, `frontend/src/types/index.ts` (paths relative to the sibling frontend repository); tests for window-state utility and existing frontend suite.

**Interfaces:** `GET /api/ycloud/status`, `POST /api/ycloud/conectar`, normalized `provider`, `botState`, `lastCustomerMessageAt` on conversations.

- [ ] Write frontend tests for channel normalization and window/state display logic; confirm failures.
- [ ] Add the YCloud channel card, validated connect action, conversation labels and window warning; rerun tests.
- [ ] Run TypeScript build and confirm polling/events update conversation list and history.

### Task 4: Bot dispatch, handoff and 24-hour enforcement

**Files:** Modify `app/services/conversas_service.py`, `app/services/chatbot_service.py`, `app/services/contact_inbox_service.py`, `app/routes/conversas.py`, `app/services/ycloud_service.py`, `frontend/src/pages/ConversationsPage.tsx`, `frontend/src/services/conversations.service.ts`; test `tests/test_ycloud_channel.py` and frontend window tests.

**Interfaces:** `PATCH /api/conversas/{id}/devolver-bot?scope=contact`; YCloud outbound returns provider message ID for status correlation.

- [ ] Write tests for correct YCloud outbound, human-only send authorization, expired window, bot suppression under takeover, return-to-bot and automatic handoff; confirm failures.
- [ ] Implement provider-specific dispatch and server window check before sending; rerun tests.
- [ ] Add scoped return-to-bot route and panel button; rerun tests.
- [ ] Run backend suite, frontend tests/build, inspect diffs and document exact remaining live-test requirements in `docs/ycloud-integration.md`.
