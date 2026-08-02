from fastapi import APIRouter, Depends

from app.core.auth import requer_admin
from app.services.supabase_service import supabase

router = APIRouter()


@router.get("/teste")
def testar_conexao(_: dict = Depends(requer_admin)):
    try:
        resposta = (
            supabase
            .table("usuarios")
            .select("id", count="exact")
            .limit(1)
            .execute()
        )
        total = getattr(resposta, "count", None)
        if total is None and resposta.data is not None:
            total = len(resposta.data)

        return {"ok": True, "conectado": True, "usuarios": total}

    except Exception as e:
        return {"ok": False, "erro": str(e)}
