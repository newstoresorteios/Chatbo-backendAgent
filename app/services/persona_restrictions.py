"""Mantém as quatro listas da Seção 9 distinguíveis dentro de `restrictions`."""

from __future__ import annotations

import re
import unicodedata
from typing import Any

GROUP_ORDER = (
    "forbiddenSubjects",
    "forbiddenPromises",
    "nonInventableInformation",
    "humanOnlyCommercialTerms",
)

PREFIXES = {
    "forbiddenSubjects": "ASSUNTO PROIBIDO — ",
    "forbiddenPromises": "NÃO PROMETER — ",
    "nonInventableInformation": "NÃO INVENTAR — ",
    "humanOnlyCommercialTerms": "SÓ COM HUMANO — ",
}

GROUP_LABELS = {
    "forbiddenSubjects": "Assuntos proibidos",
    "forbiddenPromises": "Promessas que não pode fazer",
    "nonInventableInformation": "Informações que não pode inventar",
    "humanOnlyCommercialTerms": "Condições comerciais que exigem humano",
}

CAMEL_TO_GROUP = {
    "forbiddenSubjects": "forbiddenSubjects",
    "forbiddenPromises": "forbiddenPromises",
    "nonInventableInformation": "nonInventableInformation",
    "humanOnlyCommercialTerms": "humanOnlyCommercialTerms",
}

_PREFIX_RE = re.compile(
    r"^(ASSUNTO\s+PROIBIDO|N[AÃ]O\s+PROMETER|N[AÃ]O\s+INVENTAR|S[OÓ]\s+COM\s+HUMANO)\s*[—–-]\s*",
    re.I,
)


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFD", value)
    return "".join(char for char in normalized if unicodedata.category(char) != "Mn").casefold()


_PREFIX_TO_GROUP = {
    "assunto proibido": "forbiddenSubjects",
    "nao prometer": "forbiddenPromises",
    "nao inventar": "nonInventableInformation",
    "so com humano": "humanOnlyCommercialTerms",
}


def empty_groups() -> dict[str, list[str]]:
    return {key: [] for key in GROUP_ORDER}


def split_prefixed_item(text: str) -> tuple[str | None, str]:
    raw = str(text or "").strip()
    if not raw:
        return None, ""
    match = _PREFIX_RE.match(raw)
    if not match:
        return None, raw
    group = _PREFIX_TO_GROUP.get(_fold(match.group(1)))
    rest = raw[match.end() :].strip()
    return group, rest or raw


def decode_restrictions(items: Any) -> dict[str, list[str]]:
    groups = empty_groups()
    seen = {key: set() for key in GROUP_ORDER}
    if not isinstance(items, list):
        return groups
    for item in items:
        if not isinstance(item, str):
            continue
        group, text = split_prefixed_item(item)
        if not text:
            continue
        dest = group or "nonInventableInformation"
        key = text.casefold()
        if key in seen[dest]:
            continue
        seen[dest].add(key)
        groups[dest].append(text)
    return groups


def encode_restriction_groups(groups: dict[str, list[str]] | None) -> list[str]:
    encoded: list[str] = []
    seen: set[str] = set()
    source = groups or empty_groups()
    for group in GROUP_ORDER:
        prefix = PREFIXES[group]
        for item in source.get(group) or []:
            _group, text = split_prefixed_item(str(item))
            if not text:
                continue
            key = text.casefold()
            if key in seen:
                continue
            seen.add(key)
            encoded.append(f"{prefix}{text}")
    return encoded


def has_restriction_groups(payload: dict) -> bool:
    return any(key in payload for key in CAMEL_TO_GROUP)


def groups_from_payload(payload: dict, *, clean_list) -> dict[str, list[str]]:
    groups = empty_groups()
    for key, group in CAMEL_TO_GROUP.items():
        if key in payload:
            groups[group] = clean_list(payload.get(key))
    return groups
