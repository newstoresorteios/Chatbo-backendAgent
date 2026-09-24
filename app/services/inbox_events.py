"""Server-only Realtime subscriber; browsers receive workspace-scoped invalidations."""
import asyncio
import logging
import time
from collections import OrderedDict
from uuid import uuid4
from datetime import datetime, timezone

logger = logging.getLogger(__name__)
TABLES = ("ai_inbound_messages", "ai_agent_responses", "conversas", "mensagens")


def is_new_customer_message(table, row, event_type):
    if event_type != "INSERT":
        return False
    if table == "ai_inbound_messages":
        return True
    # AI imports are already represented by the inbound event, never ring twice.
    return (table == "mensagens" and row.get("sender") == "customer"
            and not str(row.get("external_id") or "").startswith("ai-in-"))


class InboxEvents:
    def __init__(self):
        self.boot = uuid4().hex
        self.revisions = OrderedDict()
        self.condition = asyncio.Condition()
        self.queue = asyncio.Queue(maxsize=512)
        self.task = None
        self.ready = False
        self.incoming = OrderedDict()
        self.seen_incoming = OrderedDict()

    def mark_incoming(self, workspace, table, row, event_type):
        if not is_new_customer_message(table, row, event_type) or row.get("id") is None:
            return
        try:
            created = datetime.fromisoformat(str(row.get("created_at") or "").replace("Z", "+00:00"))
            timestamp = created.replace(tzinfo=created.tzinfo or timezone.utc).timestamp()
        except ValueError:
            return
        if not -5 <= time.time() - timestamp <= 60:
            return  # Historical imports/replays do not produce sounds.
        key = (workspace, table, str(row["id"]))
        if key in self.seen_incoming:
            return
        self.seen_incoming[key] = True
        self.incoming[workspace] = {"cursor": f"{self.boot}:{time.monotonic_ns()}", "at": timestamp * 1000}
        self.incoming.move_to_end(workspace)
        while len(self.seen_incoming) > 4096:
            self.seen_incoming.popitem(last=False)
        while len(self.incoming) > 2048:
            self.incoming.popitem(last=False)

    def cursor(self, workspace):
        return f"{self.boot}:{self.revisions.get(workspace, 0)}"

    async def publish(self, workspace):
        if not workspace:
            return
        async with self.condition:
            self.revisions[workspace] = time.monotonic_ns()
            self.revisions.move_to_end(workspace)
            while len(self.revisions) > 2048:
                self.revisions.popitem(last=False)
            self.condition.notify_all()

    async def wait(self, workspace, cursor, timeout=20):
        async with self.condition:
            try:
                await asyncio.wait_for(
                    self.condition.wait_for(lambda: self.cursor(workspace) != cursor), timeout
                )
            except asyncio.TimeoutError:
                pass
            current = self.cursor(workspace)
            return {"cursor": current, "changed": current != cursor, "realtime": self.ready,
                    "incoming": self.incoming.get(workspace, {"cursor": f"{self.boot}:0", "at": 0})}

    def receive(self, payload):
        data = payload.get("data") or {}
        row = data.get("record") or {}
        table = data.get("table")
        if table not in TABLES or not row.get("workspace_id"):
            return  # Legacy/null scope and DELETE payloads never fan out globally.
        try:
            self.queue.put_nowait((table, row, data.get("type")))
        except asyncio.QueueFull:
            logger.warning("Inbox Realtime queue full; polling will reconcile")

    async def consume(self):
        while True:
            table, row, event_type = await self.queue.get()
            try:
                workspace = str(row["workspace_id"])
                if table.startswith("ai_"):
                    from app.services.ai_conversas_bridge import ai_conversas_bridge
                    await asyncio.to_thread(ai_conversas_bridge.sync_event, table, row)
                from app.services.inbox_cache import conversas_cache, contact_groups_cache
                conversas_cache.delete_prefix(f"conversas:{workspace}:")
                contact_groups_cache.delete_prefix(f"contact-group:{workspace}:")
                self.mark_incoming(workspace, table, row, event_type)
                await self.publish(workspace)
            except Exception:
                logger.warning("Inbox Realtime sync failed; polling will reconcile")
            finally:
                self.queue.task_done()

    def ensure_started(self):
        if self.task is None or self.task.done():
            self.task = asyncio.create_task(self.run())

    async def run(self):
        from realtime import AsyncRealtimeClient
        from app.config.settings import SUPABASE_KEY, SUPABASE_URL
        consumer = asyncio.create_task(self.consume())
        try:
            while True:
                client = None
                try:
                    client = AsyncRealtimeClient(f"{SUPABASE_URL.rstrip('/')}/realtime/v1", SUPABASE_KEY)
                    channel = client.channel("central-server-events")
                    for table in TABLES:
                        channel.on_postgres_changes("*", self.receive, table=table, schema="public")
                    def status(state, error=None):
                        self.ready = str(getattr(state, "value", state)) == "SUBSCRIBED"
                    await channel.subscribe(status)
                    while True:
                        await asyncio.sleep(30)
                        if not self.ready:
                            break
                except Exception:
                    logger.warning("Inbox Realtime unavailable; polling remains active")
                finally:
                    self.ready = False
                    if client:
                        await client.close()
                await asyncio.sleep(10)
        finally:
            consumer.cancel()
            await asyncio.gather(consumer, return_exceptions=True)

    async def close(self):
        if self.task:
            self.task.cancel()
            await asyncio.gather(self.task, return_exceptions=True)


inbox_events = InboxEvents()
