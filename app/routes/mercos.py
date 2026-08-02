"""Rotas da API Mercos (/api/mercos/*).

Leitura: autenticado (verificar_token).
Escrita e sync: requer_permissao("manageIntegrations").
"""

import time

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.core.auth import verificar_token
from app.core.permissions import requer_permissao
from app.repositories.mercos_sync_repository import MercosSyncRepository
from app.schemas.mercos import (
    MercosClienteCreate,
    MercosPedidoCreate,
    MercosProdutoCreate,
    MercosTituloCreate,
)
from app.services.cliente_service import ClienteService
from app.services.mercos_service import MercosService, mercos_info
from app.services.pedido_service import PedidoService
from app.services.produto_service import ProdutoService
from app.services.pulsedesk_adapter import mercos_logs, mercos_status

router = APIRouter()

mercos = MercosService()
cliente_service = ClienteService()
produto_service = ProdutoService()
pedido_service = PedidoService()
sync_logs = MercosSyncRepository()

_PERM_ESCRITA = Depends(requer_permissao("manageIntegrations"))


class MercosSyncRequest(BaseModel):
    type: str = "all"
    confirmProduction: bool = False


def _registrar_sync(tipo: str, mensagem: str, quantidade: int = 0) -> None:
    sync_logs.registrar(tipo=tipo, mensagem=mensagem, quantidade=quantidade)


def _sincronizar_funil_apos_pedidos() -> str:
    from app.services.funil_sync_service import funil_sync_service

    try:
        resultado = funil_sync_service.sincronizar()
        mensagem = resultado.get("message") or "Funil sincronizado."
        sync_logs.registrar(
            tipo="funil",
            mensagem=mensagem,
            quantidade=resultado.get("dealsCreated") or 0,
            resumo=resultado,
        )
        return mensagem
    except Exception as exc:
        aviso = f"Pedidos OK, mas funil não sincronizou: {exc}"
        sync_logs.registrar(tipo="funil", mensagem=aviso, status="error")
        return aviso


def _exigir_confirmacao_producao(body: MercosSyncRequest) -> None:
    info = mercos_info()
    if not info.get("isProduction"):
        return
    if body.type == "all" and not body.confirmProduction:
        raise HTTPException(
            status_code=400,
            detail=(
                "Ambiente de PRODUÇÃO Mercos — confirme explicitamente antes de sincronizar tudo. "
                "Envie confirmProduction: true no body."
            ),
        )


def _payload(model: BaseModel) -> dict:
    return model.model_dump(exclude_none=True)


# --- Status / sync / homologação ---


@router.get("/status")
def get_mercos_status(autorizado=Depends(verificar_token)):
    return mercos_status()


@router.get("/logs")
def get_mercos_logs(autorizado=Depends(verificar_token)):
    return mercos_logs()


@router.get("/homologacao")
def get_mercos_homologacao(_: dict = _PERM_ESCRITA):
    return MercosService().status_homologacao()


@router.post("/testar-conexao")
def testar_conexao_mercos(autorizado=Depends(verificar_token)):
    try:
        clientes = MercosService().listar_clientes()
        if isinstance(clientes, dict):
            raise HTTPException(
                status_code=502,
                detail=clientes.get("mensagem") or "Resposta inválida do Mercos",
            )
        if not isinstance(clientes, list):
            raise HTTPException(status_code=502, detail="Mercos não retornou lista de clientes")
        return {
            "ok": True,
            "message": f"Mercos respondeu com sucesso ({len(clientes)} clientes na API)",
            "clientes": len(clientes),
        }
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        detail = str(exc)
        if "401" in detail:
            detail = "Token inválido ou ambiente incorreto (sandbox vs produção). Verifique MERCOS_* no Render."
        raise HTTPException(status_code=502, detail=f"Falha ao conectar com Mercos: {detail}") from exc


@router.post("/sincronizar")
def sincronizar_mercos(
    body: MercosSyncRequest,
    _: dict = _PERM_ESCRITA,
):
    tipo = body.type

    try:
        _exigir_confirmacao_producao(body)
        ambiente = mercos_info().get("environment") or "unknown"
        prefix = f"[{ambiente}] "

        if tipo == "customers":
            resultado = cliente_service.sincronizar()
            qtd = resultado.get("clientes_sincronizados", 0)
            msg = f"{prefix}Clientes sincronizados: {qtd}"
            _registrar_sync("customers", msg, qtd)
            return {"success": True, "message": msg}

        if tipo == "products":
            resultado = produto_service.sincronizar(incremental=False)
            qtd = resultado.get("produtos_sincronizados", 0)
            msg = f"{prefix}Produtos sincronizados: {qtd} (nenhum apagado)"
            _registrar_sync("products", msg, qtd)
            return {"success": True, "message": msg}

        if tipo == "orders":
            resultado = pedido_service.sincronizar()
            qtd = resultado.get("pedidos_sincronizados", 0)
            msg = resultado.get("mensagem") or f"{prefix}Pedidos sincronizados: {qtd}"
            funil_msg = _sincronizar_funil_apos_pedidos()
            return {
                "success": True,
                "message": f"{msg} {funil_msg}",
                "resumo": resultado.get("resumo"),
            }

        c = cliente_service.sincronizar()
        time.sleep(6)
        p = produto_service.sincronizar(incremental=False)
        time.sleep(6)
        o = pedido_service.sincronizar(incremental=False)
        msg = (
            f"{prefix}Sincronização concluída — "
            f"clientes: {c.get('clientes_sincronizados', 0)}, "
            f"produtos: {p.get('produtos_sincronizados', 0)}, "
            f"pedidos: {o.get('pedidos_sincronizados', 0)}"
        )
        _registrar_sync(
            "all",
            msg,
            (c.get("clientes_sincronizados", 0) + p.get("produtos_sincronizados", 0) + o.get("pedidos_sincronizados", 0)),
        )
        funil_msg = _sincronizar_funil_apos_pedidos()
        return {"success": True, "message": f"{msg}. {funil_msg}", "resumo": o.get("resumo")}
    except HTTPException:
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=f"Falha ao sincronizar com Mercos: {exc}",
        ) from exc


# --- Clientes ---


@router.get("/clientes")
def listar_clientes(autorizado=Depends(verificar_token)):
    return mercos.listar_clientes()


@router.get("/clientes/{cliente_id}")
def obter_cliente(cliente_id: int, autorizado=Depends(verificar_token)):
    return mercos.obter_cliente(cliente_id)


@router.post("/clientes")
def criar_cliente(dados: MercosClienteCreate, _: dict = _PERM_ESCRITA):
    return mercos.criar_cliente(_payload(dados))


@router.put("/clientes/{cliente_id}")
def alterar_cliente(cliente_id: int, dados: MercosClienteCreate, _: dict = _PERM_ESCRITA):
    return mercos.alterar_cliente(cliente_id, _payload(dados))


@router.post("/clientes/sincronizar")
def sincronizar_clientes(_: dict = _PERM_ESCRITA):
    return cliente_service.sincronizar()


# --- Produtos ---


@router.get("/produtos")
def listar_produtos(autorizado=Depends(verificar_token)):
    return mercos.listar_produtos()


@router.get("/produtos/{produto_id}")
def obter_produto(produto_id: int, autorizado=Depends(verificar_token)):
    return mercos.obter_produto(produto_id)


@router.post("/produtos")
def criar_produto(dados: MercosProdutoCreate, _: dict = _PERM_ESCRITA):
    return mercos.criar_produto(_payload(dados))


@router.post("/produtos/sincronizar")
def sincronizar_produtos(_: dict = _PERM_ESCRITA):
    return produto_service.sincronizar()


# --- Pedidos ---


@router.get("/pedidos")
def listar_pedidos(autorizado=Depends(verificar_token)):
    return mercos.listar_pedidos()


@router.get("/pedidos/{pedido_id}")
def obter_pedido(pedido_id: int, autorizado=Depends(verificar_token)):
    """GET usa API v1 (/pedidos/{id}). Create/update usam v2."""
    return mercos.obter_pedido(pedido_id)


@router.post("/pedidos")
def criar_pedido(dados: MercosPedidoCreate, _: dict = _PERM_ESCRITA):
    return mercos.criar_pedido(_payload(dados))


@router.put("/pedidos/{pedido_id}")
def alterar_pedido(pedido_id: int, dados: MercosPedidoCreate, _: dict = _PERM_ESCRITA):
    return mercos.alterar_pedido(pedido_id, _payload(dados))


# --- Títulos ---


@router.post("/titulos")
def criar_titulo(dados: MercosTituloCreate, _: dict = _PERM_ESCRITA):
    return mercos.criar_titulo(_payload(dados))


@router.put("/titulos/{titulo_id}")
def alterar_titulo(titulo_id: int, dados: MercosTituloCreate, _: dict = _PERM_ESCRITA):
    return mercos.alterar_titulo(titulo_id, _payload(dados))


# --- Catálogos auxiliares (leitura) ---


@router.get("/segmentos")
def listar_segmentos(autorizado=Depends(verificar_token)):
    return mercos.listar_segmentos()


@router.get("/tipos-pedido")
def listar_tipos_pedido(autorizado=Depends(verificar_token)):
    return mercos.listar_tipos_pedido()


@router.get("/usuarios-mercos")
def listar_usuarios_mercos(autorizado=Depends(verificar_token)):
    return mercos.listar_usuarios_mercos()


@router.get("/categorias")
def listar_categorias(autorizado=Depends(verificar_token)):
    return mercos.listar_categorias()


@router.get("/tabelas-preco")
def listar_tabelas_preco(autorizado=Depends(verificar_token)):
    return mercos.listar_tabelas_preco()


@router.get("/produtos-tabela-preco")
def listar_produtos_tabela_preco(autorizado=Depends(verificar_token)):
    return mercos.listar_produtos_tabela_preco()


@router.get("/condicoes-pagamento")
def listar_condicoes_pagamento(autorizado=Depends(verificar_token)):
    return mercos.listar_condicoes_pagamento()


@router.get("/transportadoras")
def listar_transportadoras(autorizado=Depends(verificar_token)):
    return mercos.listar_transportadoras()


@router.get("/politicas-comerciais")
def listar_politicas_comerciais(autorizado=Depends(verificar_token)):
    return mercos.listar_politicas_comerciais()
