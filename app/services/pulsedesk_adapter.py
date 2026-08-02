from datetime import datetime, timedelta
import math

from app.services.supabase_service import supabase
from app.repositories.dashboard_repository import DashboardRepository
from app.services.dashboard_service import DashboardService


def _paginate(items: list, page: int, page_size: int) -> dict:
    total = len(items)
    total_pages = max(1, math.ceil(total / page_size)) if page_size else 1
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "data": items[start:end],
        "total": total,
        "page": page,
        "pageSize": page_size,
        "totalPages": total_pages,
    }


def _map_cliente(row: dict) -> dict:
    nome = row.get("nome") or row.get("razao_social") or "Cliente"
    return {
        "id": str(row.get("mercos_id") or row.get("id") or nome),
        "name": nome,
        "email": row.get("email") or "",
        "phone": row.get("telefone") or row.get("celular") or "",
        "company": row.get("razao_social") or nome,
        "city": row.get("cidade") or "",
        "ordersCount": 0,
        "totalSpent": 0.0,
        "lastContact": row.get("ultima_alteracao") or datetime.utcnow().isoformat(),
        "synced": True,
    }


def _map_produto(row: dict) -> dict:
    return {
        "id": str(row.get("mercos_id") or row.get("id") or row.get("codigo") or ""),
        "code": row.get("codigo") or "",
        "name": row.get("nome") or "",
        "price": float(row.get("preco_tabela") or 0),
        "stock": int(row.get("saldo_estoque") or 0),
        "category": row.get("unidade") or "Geral",
        "synced": True,
    }


def _map_pedido(row: dict, clientes_por_id: dict | None = None) -> dict:
    status_map = {
        "1": "pending",
        "2": "processing",
        "3": "shipped",
        "4": "delivered",
        "5": "cancelled",
        "pendente": "pending",
        "processando": "processing",
        "enviado": "shipped",
        "entregue": "delivered",
        "cancelado": "cancelled",
    }
    raw_status = str(row.get("situacao") or row.get("status") or "1").lower()
    cliente_id = row.get("cliente_mercos_id") or row.get("cliente_id")
    cliente_nome = ""
    if clientes_por_id and cliente_id is not None:
        cliente = clientes_por_id.get(str(cliente_id), {})
        cliente_nome = cliente.get("nome") or cliente.get("razao_social") or ""
    if not cliente_nome and raw_status in ("1", "pendente"):
        cliente_nome = "Orçamento sem cliente"

    return {
        "id": str(row.get("mercos_id") or row.get("id") or ""),
        "number": str(row.get("numero") or row.get("mercos_id") or row.get("id") or ""),
        "customerId": str(cliente_id or ""),
        "customerName": cliente_nome,
        "status": status_map.get(raw_status, "pending"),
        "total": float(row.get("valor_total") or row.get("total") or 0),
        "createdAt": row.get("data_pedido") or row.get("created_at") or datetime.utcnow().isoformat(),
        "items": int(row.get("quantidade_itens") or row.get("itens") or 1),
    }


def _clientes_index() -> dict:
    resposta = supabase.table("clientes").select("mercos_id,nome,razao_social").execute()
    return {
        str(row.get("mercos_id")): row
        for row in (resposta.data or [])
        if row.get("mercos_id") is not None
    }


def listar_clientes(page: int = 1, page_size: int = 10, search: str = "") -> dict:
    resposta = supabase.table("clientes").select("*").execute()
    rows = resposta.data or []

    if search:
        termo = search.lower()
        rows = [
            row for row in rows
            if termo in (row.get("nome") or "").lower()
            or termo in (row.get("email") or "").lower()
            or termo in (row.get("telefone") or "").lower()
            or termo in (row.get("celular") or "").lower()
            or termo in (row.get("cidade") or "").lower()
            or termo in (row.get("razao_social") or "").lower()
        ]

    return _paginate([_map_cliente(row) for row in rows], page, page_size)


def obter_cliente(cliente_id: str) -> dict | None:
    resposta = supabase.table("clientes").select("*").eq("mercos_id", cliente_id).execute()
    rows = resposta.data or []
    if not rows:
        resposta = supabase.table("clientes").select("*").eq("id", cliente_id).execute()
        rows = resposta.data or []
    if not rows:
        return None

    cliente = _map_cliente(rows[0])
    mercos_id = str(rows[0].get("mercos_id") or cliente_id)

    try:
        pedidos_resp = (
            supabase
            .table("pedidos")
            .select("*")
            .eq("cliente_mercos_id", mercos_id)
            .order("data_pedido", desc=True)
            .execute()
        )
        pedidos_rows = pedidos_resp.data or []
    except Exception:
        pedidos_rows = []

    pedidos = [_map_pedido(row) for row in pedidos_rows]
    cliente["orders"] = pedidos
    cliente["ordersCount"] = len(pedidos)
    cliente["totalSpent"] = round(sum(float(p.get("total") or 0) for p in pedidos), 2)
    cliente["purchasedProducts"] = []
    cliente["lastService"] = cliente["lastContact"]
    if pedidos:
        cliente["lastContact"] = pedidos[0].get("createdAt") or cliente["lastContact"]
    return cliente


def listar_produtos(page: int = 1, page_size: int = 10, search: str = "", category: str | None = None) -> dict:
    resposta = supabase.table("produtos").select("*").execute()
    rows = resposta.data or []

    if search:
        termo = search.lower()
        rows = [
            row for row in rows
            if termo in (row.get("nome") or "").lower()
            or termo in (row.get("codigo") or "").lower()
        ]

    if category:
        rows = [row for row in rows if (row.get("unidade") or "Geral") == category]

    return _paginate([_map_produto(row) for row in rows], page, page_size)


def listar_pedidos(page: int = 1, page_size: int = 10, search: str = "", status: str | None = None) -> dict:
    try:
        resposta = supabase.table("pedidos").select("*").execute()
        rows = resposta.data or []
    except Exception:
        rows = []

    clientes = _clientes_index()
    mapped = [_map_pedido(row, clientes) for row in rows]

    if search:
        termo = search.lower()
        mapped = [
            item for item in mapped
            if termo in item["number"].lower()
            or termo in item["customerName"].lower()
        ]

    if status:
        mapped = [item for item in mapped if item["status"] == status]

    return _paginate(mapped, page, page_size)


def dashboard_data() -> dict:
    return DashboardService().montar()


def mercos_status() -> dict:
    from app.repositories.mercos_sync_repository import MercosSyncRepository
    from app.services.mercos_service import mercos_configurado, mercos_info
    from app.services.pedido_service import PedidoService

    repo = DashboardRepository()
    sync_repo = MercosSyncRepository()
    pedido_service = PedidoService()
    info = mercos_info()

    last_sync = sync_repo.ultima_sincronizacao("orders") or sync_repo.ultima_sincronizacao("all")
    resumo = pedido_service.resumo_situacoes()

    return {
        "connected": mercos_configurado(),
        "environment": info["environment"],
        "isProduction": info["isProduction"],
        "isSandbox": info["isSandbox"],
        "baseUrlHost": info["baseUrlHost"],
        "lastSync": last_sync or datetime.utcnow().isoformat(),
        "syncedProducts": repo.contar_produtos() or 0,
        "syncedCustomers": repo.contar_clientes() or 0,
        "syncedOrders": repo.contar_pedidos() or 0,
        "orderStatusBreakdown": resumo.get("breakdown") or [],
        "allOrdersProcessing": resumo.get("allOrdersProcessing", False),
        "retainedRevenue": resumo.get("retainedRevenue", 0),
    }


def mercos_logs() -> list:
    from app.repositories.mercos_sync_repository import MercosSyncRepository

    logs = MercosSyncRepository().listar_recentes(12)
    if not logs:
        return [
            {
                "id": "seed",
                "type": "orders",
                "status": "info",
                "message": "Nenhuma sincronização registrada ainda — use Sincronizar Pedidos.",
                "timestamp": datetime.utcnow().isoformat(),
            }
        ]

    type_map = {
        "orders": "orders",
        "products": "products",
        "customers": "customers",
        "all": "all",
        "funil": "all",
    }

    return [
        {
            "id": str(row.get("id") or ""),
            "type": type_map.get(row.get("tipo") or "orders", "orders"),
            "status": row.get("status") or "success",
            "message": row.get("mensagem") or "",
            "timestamp": row.get("created_at") or datetime.utcnow().isoformat(),
        }
        for row in logs
    ]
