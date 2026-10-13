"""Import customer pages from the company's Tray adaptor into the local catalog."""
from concurrent.futures import ThreadPoolExecutor
from collections import defaultdict
from app.services.supabase_service import supabase
from app.services.workspace_integration_service import workspace_integration_service


def customer_payload(row: dict, workspace_id: str, *, authoritative: bool = False) -> dict:
    customer = row.get("Customer", row)
    source_id = str(customer.get("id") or "").strip()
    if not source_id:
        raise ValueError("Cliente Tray sem identificador")
    fields = {
        "nome": "name", "email": "email", "telefone": "phone",
        "celular": "cellphone", "cnpj": "cnpj", "razao_social": "company_name",
        "endereco": "address", "numero": "number", "complemento": "complement",
        "bairro": "neighborhood", "cidade": "city", "estado": "state", "cep": "zip_code",
        "inscricao_estadual": "state_inscription",
    }
    payload = {"workspace_id": workspace_id, "tray_id": source_id}
    for target, source in fields.items():
        value = customer.get(source)
        # Missing fields in a list response must not erase previously imported details.
        if authoritative and source in customer and (value is None or not str(value).strip()):
            payload[target] = None
        elif value is not None and str(value).strip():
            payload[target] = str(value).strip()
    if "celular" not in payload and customer.get("mobile"):
        payload["celular"] = str(customer["mobile"]).strip()
    return payload


class TrayCustomerSync:
    def save(self, payloads):
        groups = defaultdict(list)
        for payload in payloads:
            groups[tuple(sorted(payload))].append(payload)
        for batch in groups.values():
            supabase.table("clientes").upsert(batch, on_conflict="workspace_id,tray_id").execute()

    def catalog_page(self, workspace_id: str, page: int, *, modified: str | None = None):
        client = workspace_integration_service.client_from_workspace(workspace_id)
        rows = client.list_customers(page=page, limit=50, sort="id_asc", modified=modified)
        payloads = [customer_payload(row, workspace_id) for row in rows]
        if payloads:
            previous = (supabase.table("clientes").select("tray_id,tray_modified_at,tray_contacts_pending")
                        .eq("workspace_id", workspace_id).in_("tray_id", [p["tray_id"] for p in payloads])
                        .execute().data or [])
            previous = {p["tray_id"]: p for p in previous}
            for payload, row in zip(payloads, rows):
                source_modified = str(row.get("modified") or "")
                old = previous.get(payload["tray_id"])
                payload["tray_modified_at"] = source_modified
                payload["tray_contacts_pending"] = (not old or old.get("tray_contacts_pending", True)
                                                     or old.get("tray_modified_at") != source_modified)
            self.save(payloads)
        return len(rows) < 50

    def hydrate_pending(self, workspace_id: str):
        pending = (supabase.table("clientes").select("tray_id").eq("workspace_id", workspace_id)
                   .eq("tray_contacts_pending", True).not_.is_("tray_id", "null")
                   .order("id").limit(20).execute().data or [])
        if not pending:
            return True
        client = workspace_integration_service.client_from_workspace(workspace_id)
        # Persist each successful detail, even if the next request reaches the quota.
        for row in pending:
            detail = client.customer_detail(row["tray_id"])
            if str(detail.get("id") or "") != row["tray_id"]:
                raise ValueError("Detalhe Tray não corresponde ao cliente solicitado")
            payload = customer_payload(detail, workspace_id, authoritative=True)
            payload.update(tray_contacts_pending=False, tray_modified_at=str(detail.get("modified") or ""))
            self.save([payload])
        return False

    def sync_page(self, workspace_id: str, *, page: int = 1, limit: int = 50) -> dict:
        if not workspace_id or page < 1 or not 1 <= limit <= 50:
            raise ValueError("Empresa, página ou limite inválido")
        config = workspace_integration_service.get_configured(workspace_id)
        if not config or config.get("provider") != "tray":
            raise ValueError("Esta empresa não possui integração Tray")
        client = workspace_integration_service.client_from_workspace(workspace_id)
        rows = client.list_customers(page=page, limit=limit)
        def hydrate(row):
            source = row.get("Customer", row)
            source_id = str(source.get("id") or "").strip()
            if not source_id:
                raise ValueError("Cliente Tray sem identificador")
            detail = client.customer_detail(source_id)
            if str(detail.get("id") or "") != source_id:
                raise ValueError("Detalhe Tray não corresponde ao cliente solicitado")
            payload = customer_payload({**source, **detail}, workspace_id, authoritative=True)
            payload.update(tray_contacts_pending=False, tray_modified_at=str(detail.get("modified") or ""))
            return payload

        with ThreadPoolExecutor(max_workers=4) as executor:
            payloads = list(executor.map(hydrate, rows))
        ids = [row["tray_id"] for row in payloads]
        if len(ids) != len(set(ids)):
            raise ValueError("Página Tray contém identificadores duplicados")
        self.save(payloads)
        return {"synced": len(payloads), "page": page,
                "nextPage": page + 1 if len(rows) == limit else None}


tray_customer_sync = TrayCustomerSync()
