"""Extrai texto de anexos da persona para compilar no prompt do NSAgent."""

from __future__ import annotations

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

MAX_EXTRACT_CHARS = 40_000

TEXT_EXTENSIONS = {".txt", ".md", ".markdown", ".csv", ".json", ".log"}
PDF_EXTENSIONS = {".pdf"}
ALLOWED_EXTENSIONS = TEXT_EXTENSIONS | PDF_EXTENSIONS

ALLOWED_CONTENT_TYPES = {
    "text/plain",
    "text/markdown",
    "text/csv",
    "application/json",
    "application/pdf",
    "application/octet-stream",
}


def allowed_filename(filename: str) -> bool:
    return Path(filename or "").suffix.lower() in ALLOWED_EXTENSIONS


def extract_text(filename: str, content: bytes, content_type: str | None = None) -> str:
    suffix = Path(filename or "").suffix.lower()
    ctype = (content_type or "").split(";")[0].strip().lower()

    if suffix in TEXT_EXTENSIONS or ctype.startswith("text/") or ctype == "application/json":
        return _decode_text(content)

    if suffix in PDF_EXTENSIONS or ctype == "application/pdf":
        return _extract_pdf(content)

    raise ValueError("unsupported_file_type")


def _decode_text(content: bytes) -> str:
    for encoding in ("utf-8", "utf-8-sig", "latin-1"):
        try:
            text = content.decode(encoding)
            break
        except UnicodeDecodeError:
            continue
    else:
        text = content.decode("utf-8", errors="replace")
    text = text.replace("\x00", "").strip()
    if len(text) > MAX_EXTRACT_CHARS:
        text = text[:MAX_EXTRACT_CHARS] + "\n\n[… texto truncado …]"
    return text


def _extract_pdf(content: bytes) -> str:
    try:
        from pypdf import PdfReader  # type: ignore
        from io import BytesIO
    except Exception as exc:  # pragma: no cover
        raise ValueError("pdf_support_unavailable") from exc

    reader = PdfReader(BytesIO(content))
    parts: list[str] = []
    for page in reader.pages:
        try:
            page_text = page.extract_text() or ""
        except Exception:
            page_text = ""
        if page_text.strip():
            parts.append(page_text.strip())
    text = "\n\n".join(parts).strip()
    if not text:
        raise ValueError("pdf_without_extractable_text")
    if len(text) > MAX_EXTRACT_CHARS:
        text = text[:MAX_EXTRACT_CHARS] + "\n\n[… texto truncado …]"
    return text
