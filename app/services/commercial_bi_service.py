"""Análise BI comercial: TRAYadaptor + Responses API → commercial_bi_snapshots."""

from __future__ import annotations

import json
import logging
import re
from html import unescape
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config.settings import OPENAI_API_KEY, OPENAI_MODEL
from app.repositories.contact_inbox_repository import ContactInboxRepository
from app.services.openai_provider import openai_configured
from app.services.supabase_service import supabase
from app.services.workspace_integration_service import workspace_integration_service

logger = logging.getLogger(__name__)

PHONE_RE = re.compile(r"\D+")


def _digits(value: Any) -> str:
    return PHONE_RE.sub("", str(value or ""))


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        if value is None or value == "":
            return default
        return float(str(value).replace(",", "."))
    except (TypeError, ValueError):
        return default


def _parse_datetime(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    except ValueError:
        return None


def _pick(row: dict, *keys: str) -> Any:
    for key in keys:
        if row.get(key) is not None and row.get(key) != "":
            return row.get(key)
    return None


def _order_total(order: dict) -> float:
    return _safe_float(
        _pick(
            order,
            "total",
            "Total",
            "total_order",
            "OrderTotal",
            "partial_total",
            "price",
            "valor",
        )
    )


def _order_status(order: dict) -> str:
    raw = str(
        _pick(order, "status", "Status", "order_status", "situation_id", "status_id") or ""
    ).lower()
    if any(x in raw for x in ("cancel", "canceled", "cancelled")):
        return "cancelled"
    if any(x in raw for x in ("deliver", "entreg")):
        return "delivered"
    if any(x in raw for x in ("ship", "enviad", "transit")):
        return "shipped"
    if any(x in raw for x in ("paid", "pago", "complete", "aprov")):
        return "processing"
    return "pending"


def _order_contact(order: dict) -> dict[str, str]:
    customer = order.get("Customer") if isinstance(order.get("Customer"), dict) else {}
    if not customer and isinstance(order.get("customer"), dict):
        customer = order["customer"]
    email = str(
        _pick(order, "customer_email", "email", "Email")
        or _pick(customer, "email", "Email")
        or ""
    ).strip().lower()
    phone = _digits(
        _pick(order, "customer_phone", "phone", "cellphone", "mobile")
        or _pick(customer, "phone", "cellphone", "mobile", "telephone")
    )
    name = str(
        _pick(order, "customer_name", "name")
        or _pick(customer, "name", "Name")
        or ""
    ).strip()
    return {"email": email, "phone": phone, "name": name}


def _clean_product_name(value: Any) -> str:
    name = unescape(re.sub(r"<[^>]+>", " ", str(value or "")))
    name = re.sub(r"\s*\(\s*Disponibilidade\s*:.*?\)\s*$", "", name, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", name).strip()


class CommercialBiService:
    def __init__(self) -> None:
        self.contact_inbox = ContactInboxRepository()

    def latest(self, workspace_id: str) -> dict | None:
        resposta = (
            supabase.table("commercial_bi_snapshots")
            .select("*")
            .eq("workspace_id", workspace_id)
            .eq("status", "ready")
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        rows = resposta.data or []
        return rows[0] if rows else None

    def latest_public(self, workspace_id: str) -> dict | None:
        row = self.latest(workspace_id)
        return self._response(row) if row else None

    def _response(self, row: dict) -> dict:
        return {
            "id": str(row.get("id")),
            "workspaceId": str(row.get("workspace_id")),
            "periodDays": int(row.get("period_days") or 30),
            "status": row.get("status"),
            "kpis": row.get("kpis") or {},
            "entities": row.get("entities") or {},
            "insights": row.get("insights") or {},
            "attribution": row.get("attribution") or {},
            "sourceMeta": row.get("source_meta") or {},
            "errorMessage": row.get("error_message"),
            "createdAt": row.get("created_at"),
            "completedAt": row.get("completed_at"),
        }

    def _chatbo_contacts(
        self,
        workspace_id: str,
        *,
        period_start: datetime | None = None,
    ) -> tuple[set[str], set[str], int, int, int]:
        groups = self.contact_inbox.listar(workspace_id, limit=5000)
        if period_start:
            groups = [
                group for group in groups
                if (parsed := _parse_datetime(group.get("last_message_at"))) is not None
                and parsed >= period_start
            ]
        rows = [group.get("current_session") or {} for group in groups]
        phones: set[str] = set()
        emails: set[str] = set()
        active = 0
        waiting = 0
        for row in rows:
            status = row.get("status") or "active"
            handoff_confirmed = bool(row.get("handoff_requested_at")) and row.get("handoff_reason") in {
                "customer_requested_human",
                "customer_accepted_handoff_offer",
            }
            if status == "waiting" and handoff_confirmed:
                waiting += 1
            elif status != "closed":
                active += 1
            phone = _digits(row.get("contact_phone") or row.get("phone") or "")
            if len(phone) >= 8:
                phones.add(phone[-11:] if len(phone) > 11 else phone)
            email = str(row.get("contact_email") or row.get("email") or "").strip().lower()
            if email and "@" in email:
                emails.add(email)
        return phones, emails, active, waiting, len(rows)

    def _attribute_orders(
        self,
        orders: list[dict],
        chatbo_phones: set[str],
        chatbo_emails: set[str],
    ) -> list[dict]:
        attributed: list[dict] = []
        for order in orders:
            contact = _order_contact(order)
            phone = contact["phone"]
            phone_key = phone[-11:] if len(phone) > 11 else phone
            matched = False
            if contact["email"] and contact["email"] in chatbo_emails:
                matched = True
            if phone_key and phone_key in chatbo_phones:
                matched = True
            source = "chatbo" if matched else "tray"
            attributed.append(
                {
                    "id": str(_pick(order, "id", "Id", "order_id") or ""),
                    "total": _order_total(order),
                    "status": _order_status(order),
                    "source": source,
                    "customerName": contact["name"] or None,
                    "customerEmail": contact["email"] or None,
                    "customerPhone": contact["phone"] or None,
                    "createdAt": _pick(order, "date", "created", "created_at", "OrderDate"),
                }
            )
        return attributed

    def _enrich_order_items(self, client: Any, orders: list[dict]) -> list[dict]:
        enriched: list[dict] = []
        for order in orders:
            products: list[dict] = []
            try:
                detail = client.order_complete(str(order.get("id") or ""))
                raw_products = detail.get("products") if isinstance(detail, dict) else []
                if isinstance(raw_products, list):
                    for product in raw_products:
                        if not isinstance(product, dict):
                            continue
                        quantity = max(1, int(_safe_float(product.get("quantity"), 1)))
                        products.append(
                            {
                                "productId": str(product.get("product_id") or ""),
                                "name": _clean_product_name(product.get("name")) or "Produto não informado",
                                "quantity": quantity,
                                "price": _safe_float(product.get("price")),
                            }
                        )
            except Exception as exc:
                logger.warning("Detalhes do pedido %s indisponíveis: %s", order.get("id"), exc)
            enriched.append(
                {
                    **order,
                    "items": products,
                    "itemsCount": sum(item["quantity"] for item in products) or 1,
                }
            )
        return enriched

    def _build_kpis(
        self,
        attributed_orders: list[dict],
        *,
        active_conversations: int,
        waiting_queue: int,
        customers_count: int,
        products_count: int,
    ) -> dict:
        confirmed = [o for o in attributed_orders if o["status"] in {"processing", "shipped", "delivered"}]
        delivered = [o for o in confirmed if o["status"] == "delivered"]
        pipeline = [o for o in attributed_orders if o["status"] == "pending"]
        receita = sum(o["total"] for o in confirmed)
        retida = sum(o["total"] for o in delivered)
        ticket = (receita / len(confirmed)) if confirmed else 0.0
        return {
            "receitaVendida": round(receita, 2),
            "receitaRetida": round(retida, 2),
            "pipelineEmAberto": round(sum(o["total"] for o in pipeline), 2),
            "oportunidadesEmAberto": len(pipeline),
            "pedidosConfirmados": len(confirmed),
            "pedidosEntregues": len(delivered),
            "pedidosEnviados": sum(1 for o in confirmed if o["status"] == "shipped"),
            "receitaEnviada": round(sum(o["total"] for o in confirmed if o["status"] == "shipped"), 2),
            "pedidosPorStatus": {
                status: sum(1 for order in attributed_orders if order["status"] == status)
                for status in ("pending", "processing", "shipped", "delivered", "cancelled")
            },
            "valoresPorStatus": {
                status: round(sum(order["total"] for order in attributed_orders if order["status"] == status), 2)
                for status in ("pending", "processing", "shipped", "delivered", "cancelled")
            },
            "conversasAtivas": active_conversations,
            "waitingQueue": waiting_queue,
            "totalCustomers": customers_count,
            "totalProducts": products_count,
            "ticketMedio": round(ticket, 2),
            "dataScope": "chatbo_current_month",
        }

    def _entities(
        self,
        attributed_orders: list[dict],
    ) -> dict:
        customers_by_key: dict[str, dict] = {}
        for order in attributed_orders:
            key = str(order.get("customerPhone") or order.get("customerEmail") or order.get("customerName") or order["id"])
            customer = customers_by_key.setdefault(key, {
                "id": key,
                "name": order.get("customerName") or "Contato ChatBô",
                "email": order.get("customerEmail"),
                "phone": order.get("customerPhone"),
                "ordersCount": 0,
                "totalSpent": 0.0,
                "lastContact": order.get("createdAt"),
                "source": "chatbo",
            })
            if order["status"] != "cancelled":
                customer["ordersCount"] += 1
                customer["totalSpent"] = round(customer["totalSpent"] + order["total"], 2)
            if str(order.get("createdAt") or "") > str(customer.get("lastContact") or ""):
                customer["lastContact"] = order.get("createdAt")
        return {
            "customers": list(customers_by_key.values())[:40],
            "products": [],
            "orders": attributed_orders[:80],
        }

    def _call_responses_insights(self, context: dict) -> dict:
        if not openai_configured():
            return {
                "summary": "Análise determinística (OpenAI não configurada).",
                "actions": [
                    "Configure OPENAI_API_KEY no backend para insights de vendas via Responses API.",
                ],
                "model": None,
            }

        schema_hint = {
            "summary": "string curta em pt-BR",
            "actions": ["lista de 3 a 5 ações concretas para aumentar vendas"],
            "risks": ["gargalos ou riscos"],
            "opportunities": ["oportunidades atribuídas ao ChatBô no mês atual"],
        }
        prompt = (
            "Você é analista de BI comercial da New Store / ChatBô. "
            "Com base somente nos resultados atribuídos ao ChatBô no mês atual, "
            "retorne APENAS JSON válido no formato: "
            f"{json.dumps(schema_hint, ensure_ascii=False)}. "
            "Não invente números fora do contexto.\n\n"
            f"CONTEXTO:\n{json.dumps(context, ensure_ascii=False)[:60000]}"
        )
        model = OPENAI_MODEL or "gpt-4o-mini"
        payload = {
            "model": model,
            "input": [
                {
                    "role": "user",
                    "content": [{"type": "input_text", "text": prompt}],
                }
            ],
            "text": {"format": {"type": "json_object"}},
        }
        try:
            response = httpx.post(
                "https://api.openai.com/v1/responses",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json=payload,
                timeout=120.0,
            )
            if response.status_code >= 400:
                # Fallback chat completions
                return self._call_chat_insights(context, model)
            data = response.json()
            text = self._extract_responses_text(data)
            parsed = json.loads(text) if text else {}
            if isinstance(parsed, dict):
                parsed["model"] = model
                parsed["via"] = "responses"
                return parsed
        except Exception as exc:
            logger.warning("Responses API falhou, fallback chat: %s", exc)
            return self._call_chat_insights(context, model)
        return self._call_chat_insights(context, model)

    def _extract_responses_text(self, data: dict) -> str:
        # Responses API: output[].content[].text
        output = data.get("output") or []
        chunks: list[str] = []
        for item in output:
            for part in item.get("content") or []:
                if isinstance(part, dict) and part.get("type") in {"output_text", "text"}:
                    if part.get("text"):
                        chunks.append(str(part["text"]))
        if chunks:
            return "\n".join(chunks).strip()
        # some SDKs expose output_text
        if isinstance(data.get("output_text"), str):
            return data["output_text"].strip()
        return ""

    def _call_chat_insights(self, context: dict, model: str) -> dict:
        try:
            response = httpx.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": model,
                    "temperature": 0.3,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {
                            "role": "system",
                            "content": "Analista BI comercial. Responda só JSON com summary, actions, risks, opportunities.",
                        },
                        {
                            "role": "user",
                            "content": json.dumps(context, ensure_ascii=False)[:60000],
                        },
                    ],
                },
                timeout=120.0,
            )
            response.raise_for_status()
            content = (((response.json().get("choices") or [{}])[0].get("message") or {}).get("content")) or "{}"
            parsed = json.loads(content)
            if isinstance(parsed, dict):
                parsed["model"] = model
                parsed["via"] = "chat.completions"
                return parsed
        except Exception as exc:
            logger.warning("Chat insights falhou: %s", exc)
        return {
            "summary": "KPIs do ChatBô calculados para o mês atual; insights indisponíveis.",
            "actions": [],
            "model": model,
            "via": "deterministic",
        }

    def analyze(
        self,
        workspace_id: str,
        *,
        user_id: str | None = None,
        period_days: int = 30,
    ) -> dict:
        month_start = datetime.now(timezone.utc).replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        period_days = max(1, (datetime.now(timezone.utc).date() - month_start.date()).days + 1)
        running = {
            "workspace_id": workspace_id,
            "period_days": period_days,
            "status": "running",
            "kpis": {},
            "entities": {},
            "insights": {},
            "attribution": {},
            "source_meta": {},
            "created_by": user_id,
        }
        created = (
            supabase.table("commercial_bi_snapshots").insert(running).execute().data or []
        )
        snap_id = (created[0] if created else {}).get("id")

        try:
            client = workspace_integration_service.client_from_workspace(workspace_id)
            sample = client.collect_period(
                period_days=period_days,
                page_size=50,
                max_pages=40,
                product_pages=0,
                customer_pages=0,
                calendar_month=True,
            )
            phones, emails, active, waiting, total_contacts = self._chatbo_contacts(
                workspace_id,
                period_start=month_start,
            )
            attributed = self._attribute_orders(sample["orders"], phones, emails)
            chatbo_orders = [order for order in attributed if order["source"] == "chatbo"]
            chatbo_orders = self._enrich_order_items(client, chatbo_orders)
            kpis = self._build_kpis(
                chatbo_orders,
                active_conversations=active,
                waiting_queue=waiting,
                customers_count=total_contacts,
                products_count=0,
            )
            kpis["totalContacts"] = total_contacts
            kpis["dataScope"] = "chatbo_current_month"
            entities = self._entities(chatbo_orders)
            chatbo_count = len(chatbo_orders)
            attribution = {
                "rule": "chatbo_contact_match",
                "ordersChatbo": chatbo_count,
                "matchedByPhoneOrEmail": chatbo_count,
            }
            insight_context = {
                "kpis": kpis,
                "attribution": attribution,
                "period": sample.get("period"),
                "sampleOrders": chatbo_orders[:30],
                "activeConversations": active,
            }
            insights = self._call_responses_insights(insight_context)
            source_meta = {
                "period": sample.get("period"),
                "attributedOrders": chatbo_count,
                "scope": "chatbo_current_month",
            }
            update = {
                "status": "ready",
                "kpis": kpis,
                "entities": entities,
                "insights": insights,
                "attribution": attribution,
                "source_meta": source_meta,
                "completed_at": datetime.utcnow().isoformat(),
                "error_message": None,
            }
            if snap_id:
                supabase.table("commercial_bi_snapshots").update(update).eq("id", snap_id).execute()
            # marca sync da integração
            integ = workspace_integration_service.get(workspace_id, "tray")
            if integ:
                supabase.table("workspace_integrations").update(
                    {
                        "last_sync_at": datetime.utcnow().isoformat(),
                        "last_sync_status": "success",
                        "last_error": None,
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", integ["id"]).execute()

            row = self.latest(workspace_id) or {**running, **update, "id": snap_id}
            return self._response(row)
        except Exception as exc:
            logger.exception("commercial BI analyze failed workspace=%s", workspace_id)
            if snap_id:
                supabase.table("commercial_bi_snapshots").update(
                    {
                        "status": "failed",
                        "error_message": str(exc)[:800],
                        "completed_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", snap_id).execute()
            integ = workspace_integration_service.get(workspace_id, "tray")
            if integ:
                supabase.table("workspace_integrations").update(
                    {
                        "last_sync_status": "error",
                        "last_error": str(exc)[:500],
                        "status": "error",
                        "updated_at": datetime.utcnow().isoformat(),
                    }
                ).eq("id", integ["id"]).execute()
            raise


commercial_bi_service = CommercialBiService()
