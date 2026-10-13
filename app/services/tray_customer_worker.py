"""Persistent per-company synchronization with atomic leases across server instances."""
import asyncio
import logging
from datetime import datetime, timedelta, timezone
from uuid import uuid4
from zoneinfo import ZoneInfo
from concurrent.futures import ThreadPoolExecutor

from app.services.supabase_service import supabase
from app.services.tray_customer_sync import tray_customer_sync

logger = logging.getLogger(__name__)
SAO_PAULO = ZoneInfo("America/Sao_Paulo")


def parse_time(value):
    return datetime.fromisoformat(str(value).replace("Z", "+00:00")) if value else None


class TrayCustomerWorker:
    def tick(self):
        integrations = (supabase.table("workspace_integrations").select("workspace_id")
                        .eq("provider", "tray").eq("status", "connected").execute().data or [])
        for integration in integrations:
            workspace_id = integration["workspace_id"]
            supabase.table("tray_customer_sync_state").upsert(
                {"workspace_id": workspace_id}, on_conflict="workspace_id", ignore_duplicates=True
            ).execute()
            now = datetime.now(timezone.utc)
            token = str(uuid4())
            claimed = (supabase.table("tray_customer_sync_state")
                       .update({"lease_until": (now + timedelta(minutes=10)).isoformat(), "lease_token": token})
                       .eq("workspace_id", workspace_id).lte("lease_until", now.isoformat())
                       .lte("next_run_at", now.isoformat()).execute().data or [])
            if not claimed:
                continue
            state = claimed[0]
            patch = {"last_error": None, "next_run_at": now.isoformat()}
            try:
                patch.update(self.advance(workspace_id, state, now))
            except Exception as exc:
                error = str(exc).lower()
                daily = "quota" in error and ("day" in error or "daily" in error)
                patch["last_error"] = "tray_daily_limit" if daily else "tray_rate_limit" if "429" in error else "sync_failed"
                patch["next_run_at"] = (now + timedelta(hours=1) if daily
                                         else now + timedelta(minutes=2)).isoformat()
                logger.warning("Tray customer sync deferred workspace=%s reason=%s", workspace_id, patch["last_error"])
            patch.update(lease_until=datetime.now(timezone.utc).isoformat(), lease_token=None,
                         updated_at=datetime.now(timezone.utc).isoformat())
            (supabase.table("tray_customer_sync_state").update(patch)
             .eq("workspace_id", workspace_id).eq("lease_token", token).execute())

    def advance(self, workspace_id, state, now):
        phase = state["phase"]
        today = now.astimezone(SAO_PAULO).date()
        if phase == "idle":
            full_at = parse_time(state.get("last_full_at"))
            if not full_at or now - full_at >= timedelta(days=1):
                return {"phase": "catalog", "next_page": 1}
            last_at = parse_time(state.get("last_scan_at")) or now
            return {"phase": "incremental", "next_page": 1,
                    "scan_date": last_at.astimezone(SAO_PAULO).date().isoformat()}
        if phase in {"catalog", "incremental"}:
            page = state["next_page"]
            if phase == "catalog":
                with ThreadPoolExecutor(max_workers=4) as executor:
                    results = list(executor.map(lambda p: tray_customer_sync.catalog_page(workspace_id, p),
                                                range(page, page + 4)))
                done = any(results)
                next_page = page + 4
            else:
                done = tray_customer_sync.catalog_page(workspace_id, page, modified=state.get("scan_date"))
                next_page = page + 1
            if not done:
                return {"next_page": next_page}
            if phase == "incremental" and str(state["scan_date"]) < today.isoformat():
                from datetime import date
                next_date = date.fromisoformat(str(state["scan_date"])) + timedelta(days=1)
                return {"next_page": 1, "scan_date": next_date.isoformat()}
            patch = {"phase": "contacts", "next_page": 1, "last_scan_at": now.isoformat()}
            if phase == "catalog":
                patch["last_full_at"] = now.isoformat()
            return patch
        full_at = parse_time(state.get("last_full_at"))
        scan_at = parse_time(state.get("last_scan_at"))
        if full_at and now - full_at >= timedelta(days=1):
            return {"phase": "catalog", "next_page": 1}
        if not scan_at:
            return {"last_scan_at": now.isoformat()}
        if scan_at and now - scan_at >= timedelta(minutes=15):
            return {"phase": "incremental", "next_page": 1,
                    "scan_date": scan_at.astimezone(SAO_PAULO).date().isoformat()}
        if tray_customer_sync.hydrate_pending(workspace_id):
            return {"phase": "idle", "last_completed_at": now.isoformat(),
                    "next_run_at": (now + timedelta(minutes=15)).isoformat()}
        return {"next_run_at": (now + timedelta(seconds=35)).isoformat()}

    async def run(self):
        while True:
            try:
                await asyncio.to_thread(self.tick)
            except asyncio.CancelledError:
                raise
            except Exception:
                logger.exception("Tray customer worker failed")
                await asyncio.sleep(30)
            await asyncio.sleep(2)


tray_customer_worker = TrayCustomerWorker()
