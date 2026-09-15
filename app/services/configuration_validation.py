"""Validate operator values against the catalog persisted in PostgreSQL."""
from __future__ import annotations

from math import isfinite
from string import Formatter
from typing import Any
import json
from urllib.parse import urlparse
from fastapi import HTTPException


def validate_structured(value: str, schema: str) -> None:
    parsed = json.loads(value)
    if not isinstance(parsed, list) or not parsed or len(parsed) > 100:
        raise ValueError("informe uma lista JSON com 1 a 100 itens")
    if schema == "creditBands":
        previous = -1
        for band in parsed:
            if (not isinstance(band, list) or len(band) != 3
                    or any(type(v) is not int or v <= 0 for v in band)
                    or band[0] > band[1] or band[0] <= previous or band[2] <= band[1]):
                raise ValueError("faixas em centavos devem ser positivas, ordenadas e sem sobreposição")
            previous = band[1]
    elif schema == "greetingVariants":
        for item in parsed:
            if not isinstance(item, str) or not item.strip() or len(item) > 1000:
                raise ValueError("saudações devem ser textos de até 1000 caracteres")
            for _, field, spec, conversion in Formatter().parse(item):
                if field is not None and (field != "agent_name" or spec or conversion):
                    raise ValueError("a única variável permitida é {agent_name}")
    elif schema == "institutionalKnowledge":
        for item in parsed:
            if (not isinstance(item, dict) or not isinstance(item.get("title"), str)
                    or not isinstance(item.get("body"), str) or not isinstance(item.get("cues"), list)
                    or any(not isinstance(cue, str) or not cue.strip() for cue in item["cues"])
                    or item.get("policyKey") not in {None, "acceptsTradeIn"}):
                raise ValueError("cada item deve ter title, body e cues válidos")
    else:
        raise ValueError("formato estruturado desconhecido")


def validate_values(values: dict, fields: list[dict], *, current: dict | None = None) -> dict:
    by_key = {field["key"]: field for field in fields}
    unknown = set(values) - by_key.keys()
    if unknown:
        raise HTTPException(status_code=422, detail="Campos não cadastrados: " + ", ".join(sorted(unknown)))
    result = {field["key"]: field.get("default") for field in fields}
    result.update({k: v for k, v in (current or {}).items() if k in by_key})
    result.update(values)
    for key, value in result.items():
        field = by_key[key]
        kind = field["type"]
        error = None
        if field.get("readOnly") and value != (current or {}).get(key, field.get("default")):
            error = "campo protegido"
        elif kind == "boolean" and not isinstance(value, bool):
            error = "informe verdadeiro ou falso"
        elif kind in {"integer", "number"}:
            if isinstance(value, bool) or not isinstance(value, (int, float)) or not isfinite(value):
                error = "informe um número válido"
            elif kind == "integer" and int(value) != value:
                error = "informe um número inteiro"
            elif field.get("min") is not None and value < field["min"]:
                error = f"mínimo: {field['min']}"
            elif field.get("max") is not None and value > field["max"]:
                error = f"máximo: {field['max']}"
        elif kind == "select" and value not in [opt["value"] for opt in field.get("options", [])]:
            error = "opção inválida"
        elif kind in {"text", "textarea"}:
            if not isinstance(value, str) or len(value) > field.get("maxLength", 20000):
                error = "texto inválido ou muito longo"
        if not error and field.get("target") == "message":
            try:
                def slots(text):
                    names = set()
                    for _, name, spec, conversion in Formatter().parse(text):
                        if name is not None:
                            if not name.isidentifier() or spec or conversion:
                                raise ValueError("unsafe variable")
                            names.add(name)
                    return names
                if slots(value) != slots(field["default"]) or not value.strip():
                    error = "preserve as variáveis e preencha o texto"
            except (ValueError, TypeError):
                error = "variáveis de mensagem inválidas"
        if not error and field.get("valueSchema"):
            try:
                validate_structured(value, field["valueSchema"])
            except (ValueError, TypeError) as exc:
                error = str(exc)
        if not error and key.startswith("business.") and key.endswith("_url"):
            parsed_url = urlparse(value)
            if parsed_url.scheme != "https" or not parsed_url.hostname or parsed_url.username or parsed_url.password:
                error = "informe uma URL HTTPS oficial, sem credenciais"
        if error:
            raise HTTPException(status_code=422, detail=f"{field['label']}: {error}")
    return result
