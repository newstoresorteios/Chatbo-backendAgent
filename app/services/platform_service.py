import uuid
from collections import defaultdict
from datetime import datetime

from fastapi import HTTPException

from app.repositories.platform_repository import PlatformRepository
from app.services.supabase_service import supabase


def _iso(value) -> str | None:
    if value is None:
        return None
    if isinstance(value, str):
        return value
    return value.isoformat()


def _map_canal(row: dict) -> dict:
    item = {
        "id": str(row["id"]),
        "type": row["type"],
        "name": row["name"],
        "connected": bool(row.get("connected", True)),
        "messagesToday": int(row.get("messages_today") or 0),
    }
    if row.get("phone"):
        item["phone"] = row["phone"]
    if row.get("display_phone"):
        item["phone"] = row["display_phone"]
    if row.get("last_activity"):
        item["lastActivity"] = _iso(row["last_activity"])
    if row.get("provider"):
        item["provider"] = row["provider"]
    if row.get("provider_status"):
        item["providerStatus"] = row["provider_status"]
    return item


def _map_campanha(row: dict) -> dict:
    item = {
        "id": str(row["id"]),
        "name": row["name"],
        "channel": row["channel"],
        "status": row["status"],
        "recipients": int(row.get("recipients") or 0),
        "sent": int(row.get("sent") or 0),
        "opened": int(row.get("opened") or 0),
        "failed": int(row.get("failed") or 0),
    }
    if row.get("message"):
        item["message"] = row["message"]
    if row.get("scheduled_at"):
        item["scheduledAt"] = _iso(row["scheduled_at"])
    if row.get("dispatched_at"):
        item["dispatchedAt"] = _iso(row["dispatched_at"])
    if row.get("last_error"):
        item["lastError"] = row["last_error"]
    return item


def _map_chatbot(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "channel": row["channel"],
        "active": bool(row.get("active", True)),
        "triggers": int(row.get("triggers") or 0),
        "resolved": int(row.get("resolved") or 0),
    }


def _map_integracao(row: dict) -> dict:
    return {
        "id": str(row["id"]),
        "name": row["name"],
        "category": row["category"],
        "connected": bool(row.get("connected", False)),
    }


class PlatformService:

    def __init__(self):
        self.repo = PlatformRepository()

    def _ensure_tables(self) -> None:
        try:
            supabase.table("canais").select("id").limit(0).execute()
        except Exception as exc:
            if "canais" in str(exc).lower() or "relation" in str(exc).lower():
                raise HTTPException(
                    status_code=503,
                    detail=(
                        "Tabelas da plataforma não existem. "
                        "Execute supabase/003_platform.sql no Supabase e rode scripts/seed_platform.py."
                    ),
                ) from exc
            raise

    def _handle_db_error(self, exc: Exception) -> None:
        msg = str(exc).lower()
        if "canais" in msg or "funil" in msg or "campanhas" in msg or "integracoes" in msg or "relation" in msg:
            raise HTTPException(
                status_code=503,
                detail=(
                    "Tabelas da plataforma não existem. "
                    "Execute supabase/003_platform.sql no Supabase e rode scripts/seed_platform.py."
                ),
            ) from exc
        raise

    # Canais
    def get_channels(self) -> list[dict]:
        self._ensure_tables()
        try:
            rows = self.repo.list_canais()
            msg_counts = self._messages_today_by_channel_type()
        except Exception as exc:
            self._handle_db_error(exc)
        result = []
        for row in rows:
            item = _map_canal(row)
            item["messagesToday"] = msg_counts.get(row.get("type"), 0)
            result.append(item)
        return result

    def _messages_today_by_channel_type(self) -> dict[str, int]:
        hoje = datetime.utcnow().date()
        try:
            conversas = supabase.table("conversas").select("id,channel").execute().data or []
            mensagens = supabase.table("mensagens").select("conversa_id,created_at").execute().data or []
        except Exception:
            return {}

        canal_por_conversa = {str(c["id"]): c.get("channel") or "whatsapp" for c in conversas}
        counts: dict[str, int] = defaultdict(int)

        for msg in mensagens:
            dt_raw = msg.get("created_at")
            if not dt_raw:
                continue
            try:
                dt = datetime.fromisoformat(str(dt_raw).replace("Z", "+00:00")).replace(tzinfo=None)
            except ValueError:
                continue
            if dt.date() != hoje:
                continue
            channel = canal_por_conversa.get(str(msg.get("conversa_id")), "whatsapp")
            counts[channel] += 1

        return dict(counts)

    def connect_channel(self, channel_type: str, name: str) -> dict:
        self._ensure_tables()
        connected = False
        provider_status = "pending"
        provider = "manual"

        if channel_type == "whatsapp":
            from app.services.whatsapp_service import whatsapp_service

            status = whatsapp_service.status()
            connected = bool(status.get("connected"))
            provider_status = status.get("providerStatus") or ("active" if connected else "pending")
            provider = "meta"

        dados = {
            "id": f"ch-{uuid.uuid4().hex[:8]}",
            "type": channel_type,
            "name": name,
            "connected": connected,
            "provider": provider,
            "provider_status": provider_status,
            "messages_today": 0,
            "last_activity": datetime.utcnow().isoformat(),
        }
        try:
            row = self.repo.create_canal(dados)
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_canal(row)

    def update_channel(self, channel_id: str, patch: dict) -> dict | None:
        self._ensure_tables()
        db_patch = {}
        if "name" in patch:
            db_patch["name"] = patch["name"]
        if "phone" in patch:
            db_patch["phone"] = patch["phone"]
        if "connected" in patch:
            db_patch["connected"] = patch["connected"]
        if not db_patch:
            return _map_canal(self.repo.get_canal(channel_id)) if self.repo.get_canal(channel_id) else None
        try:
            row = self.repo.update_canal(channel_id, db_patch)
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_canal(row) if row else None

    def toggle_channel(self, channel_id: str) -> dict | None:
        self._ensure_tables()
        canal = self.repo.get_canal(channel_id)
        if not canal:
            return None
        try:
            row = self.repo.update_canal(channel_id, {
                "connected": not bool(canal.get("connected")),
                "last_activity": datetime.utcnow().isoformat(),
            })
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_canal(row) if row else None

    # Funil
    def get_funnel(self) -> list[dict]:
        self._ensure_tables()
        try:
            estagios = self.repo.list_estagios()
            negocios = self.repo.list_negocios()
        except Exception as exc:
            self._handle_db_error(exc)

        negocios_por_estagio: dict[str, list[dict]] = {}
        for negocio in negocios:
            stage_id = str(negocio["stage_id"])
            negocios_por_estagio.setdefault(stage_id, []).append({
                "id": str(negocio["id"]),
                "title": negocio["title"],
                "contact": negocio["contact"],
                "value": float(negocio.get("value") or 0),
                "channel": negocio["channel"],
                "stageId": stage_id,
            })

        return [
            {
                "id": str(estagio["id"]),
                "name": estagio["name"],
                "deals": negocios_por_estagio.get(str(estagio["id"]), []),
            }
            for estagio in estagios
        ]

    def move_deal(self, deal_id: str, stage_id: str) -> bool:
        self._ensure_tables()
        negocio = self.repo.get_negocio(deal_id)
        if not negocio:
            return False
        estagios = {str(e["id"]) for e in self.repo.list_estagios()}
        if stage_id not in estagios:
            return False
        try:
            row = self.repo.update_negocio(deal_id, {"stage_id": stage_id})
        except Exception as exc:
            self._handle_db_error(exc)
        return row is not None

    # Campanhas
    def get_campaigns(self) -> list[dict]:
        self._ensure_tables()
        try:
            rows = self.repo.list_campanhas()
        except Exception as exc:
            self._handle_db_error(exc)
        return [_map_campanha(row) for row in rows]

    def add_campaign(self, campaign: dict) -> dict:
        self._ensure_tables()
        dados = {
            "id": f"cp-{uuid.uuid4().hex[:8]}",
            "name": campaign["name"],
            "channel": campaign["channel"],
            "status": campaign.get("status", "draft"),
            "recipients": int(campaign.get("recipients") or 0),
            "sent": 0,
            "opened": 0,
            "failed": 0,
        }
        if campaign.get("message"):
            dados["message"] = campaign["message"].strip()
        if campaign.get("scheduledAt"):
            dados["scheduled_at"] = campaign["scheduledAt"]
        try:
            row = self.repo.create_campanha(dados)
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_campanha(row)

    def dispatch_campaign(self, campaign_id: str) -> dict:
        from app.services.campaign_service import campaign_service

        self._ensure_tables()
        return campaign_service.disparar(campaign_id)

    # Chatbot
    def get_chatbots(self) -> list[dict]:
        self._ensure_tables()
        try:
            rows = self.repo.list_chatbots()
        except Exception as exc:
            self._handle_db_error(exc)
        return [_map_chatbot(row) for row in rows]

    def add_chatbot(self, flow: dict) -> dict:
        self._ensure_tables()
        dados = {
            "id": f"bot-{uuid.uuid4().hex[:8]}",
            "name": flow["name"],
            "channel": flow["channel"],
            "active": bool(flow.get("active", True)),
            "triggers": 0,
            "resolved": 0,
        }
        try:
            row = self.repo.create_chatbot(dados)
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_chatbot(row)

    def toggle_chatbot(self, flow_id: str) -> dict | None:
        self._ensure_tables()
        flow = self.repo.get_chatbot(flow_id)
        if not flow:
            return None
        try:
            row = self.repo.update_chatbot(flow_id, {"active": not bool(flow.get("active"))})
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_chatbot(row) if row else None

    def update_chatbot(self, flow_id: str, patch: dict) -> dict | None:
        self._ensure_tables()
        db_patch = {}
        if "name" in patch:
            db_patch["name"] = patch["name"]
        if "active" in patch:
            db_patch["active"] = patch["active"]
        if not db_patch:
            flow = self.repo.get_chatbot(flow_id)
            return _map_chatbot(flow) if flow else None
        try:
            row = self.repo.update_chatbot(flow_id, db_patch)
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_chatbot(row) if row else None

    # Integrações
    def get_integrations(self) -> list[dict]:
        self._ensure_tables()
        try:
            rows = self.repo.list_integracoes()
        except Exception as exc:
            self._handle_db_error(exc)
        return [_map_integracao(row) for row in rows]

    def toggle_integration(self, integration_id: str) -> dict | None:
        self._ensure_tables()
        item = self.repo.get_integracao(integration_id)
        if not item:
            return None
        try:
            row = self.repo.update_integracao(integration_id, {
                "connected": not bool(item.get("connected")),
            })
        except Exception as exc:
            self._handle_db_error(exc)
        return _map_integracao(row) if row else None


platform_service = PlatformService()
