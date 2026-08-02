"""Resolve conversas.cliente_id a partir de clientes (Mercos id ou telefone)."""

from __future__ import annotations

import logging
import re

from app.services.supabase_service import supabase

logger = logging.getLogger(__name__)

_DIGITS = re.compile(r"\D+")


def normalizar_telefone_cliente(valor: str | int | None) -> str | None:
    if valor is None:
        return None
    digitos = _DIGITS.sub("", str(valor))
    if len(digitos) < 10:
        return None
    if len(digitos) in (10, 11) and not digitos.startswith("55"):
        digitos = f"55{digitos}"
    return digitos


def _buscar_id_por_mercos(cliente_mercos_id: str | int) -> str | None:
    texto = str(cliente_mercos_id).strip()
    if not texto or not texto.isdigit():
        return None
    try:
        resposta = (
            supabase.table("clientes")
            .select("id")
            .eq("mercos_id", int(texto))
            .limit(1)
            .execute()
        )
    except Exception as exc:
        logger.warning("Falha ao buscar cliente por mercos_id=%s: %s", texto, exc)
        return None
    rows = resposta.data or []
    if not rows:
        return None
    cid = rows[0].get("id")
    return str(cid) if cid else None


def _buscar_id_por_telefone(telefone: str) -> str | None:
    tel = normalizar_telefone_cliente(telefone)
    if not tel:
        return None
    for campo in ("telefone", "celular"):
        try:
            resposta = (
                supabase.table("clientes")
                .select("id")
                .eq(campo, tel)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            logger.warning("Falha ao buscar cliente por %s=%s: %s", campo, tel[-4:], exc)
            continue
        rows = resposta.data or []
        if rows and rows[0].get("id"):
            return str(rows[0]["id"])
    return None


def resolver_cliente_id_conversa(
    *,
    cliente_mercos_id: str | int | None = None,
    telefone: str | None = None,
) -> str | None:
    """Retorna clientes.id (uuid) ou None. Não inventa vínculo."""
    if cliente_mercos_id is not None and str(cliente_mercos_id).strip():
        encontrado = _buscar_id_por_mercos(cliente_mercos_id)
        if encontrado:
            return encontrado
    if telefone:
        return _buscar_id_por_telefone(telefone)
    return None


def enriquecer_dados_conversa_com_cliente_id(
    dados: dict,
    *,
    existente: dict | None = None,
) -> dict:
    """Inclui cliente_id no payload se ainda estiver vazio e houver match."""
    out = dict(dados)
    if out.get("cliente_id"):
        return out
    if existente and existente.get("cliente_id"):
        return out

    mercos = out.get("cliente_mercos_id")
    if mercos is None and existente:
        mercos = existente.get("cliente_mercos_id")

    telefone = (
        out.get("contact_phone")
        or out.get("external_thread_id")
        or (existente or {}).get("contact_phone")
        or (existente or {}).get("external_thread_id")
    )

    resolvido = resolver_cliente_id_conversa(
        cliente_mercos_id=mercos,
        telefone=telefone,
    )
    if resolvido:
        out["cliente_id"] = resolvido
    return out
