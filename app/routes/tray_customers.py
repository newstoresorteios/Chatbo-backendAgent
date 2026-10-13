from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from app.core.permissions import requer_permissao
from app.core.workspace_scope import obter_company_context, workspace_id_from_context
from app.services.tray_customer_sync import tray_customer_sync

router = APIRouter()


@router.get("/tray/clientes/sincronizacao")
def sync_status(context: dict = Depends(obter_company_context)):
    from app.services.supabase_service import supabase
    workspace_id = workspace_id_from_context(context)
    rows = (supabase.table("tray_customer_sync_state").select(
        "phase,next_page,last_full_at,last_completed_at,last_scan_at,next_run_at,last_error"
    ).eq("workspace_id", workspace_id).limit(1).execute().data or [])
    total = (supabase.table("clientes").select("id", count="exact", head=True)
             .eq("workspace_id", workspace_id).not_.is_("tray_id", "null").execute().count or 0)
    pending = (supabase.table("clientes").select("id", count="exact", head=True)
               .eq("workspace_id", workspace_id).not_.is_("tray_id", "null")
               .eq("tray_contacts_pending", True).execute().count or 0)
    return {"total": total, "pendingContacts": pending, "state": rows[0] if rows else None}


class CustomerSyncRequest(BaseModel):
    page: int = Field(default=1, ge=1)
    limit: int = Field(default=50, ge=1, le=50)


@router.post("/tray/clientes/sincronizar")
def sync_customers(body: CustomerSyncRequest,
                   context: dict = Depends(obter_company_context),
                   _=Depends(requer_permissao("manageIntegrations"))):
    try:
        return tray_customer_sync.sync_page(
            workspace_id_from_context(context), page=body.page, limit=body.limit
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except HTTPException:
        raise
    except Exception as exc:
        # Upstream errors may include internal credentials or personal data.
        raise HTTPException(status_code=502, detail="Falha ao sincronizar clientes da Tray. Repita esta página.") from exc
