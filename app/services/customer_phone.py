import re


def whatsapp_phone(value: str | None) -> str:
    """Normalize Brazilian local numbers and explicitly international numbers."""
    raw = str(value or "").strip()
    digits = re.sub(r"\D", "", raw)
    if raw.startswith("+") or raw.startswith("00"):
        digits = digits[2:] if raw.startswith("00") else digits
        return digits if 10 <= len(digits) <= 15 and not digits.startswith("0") else ""
    if len(digits) in (10, 11) and not digits.startswith("0"):
        return "55" + digits
    if len(digits) in (12, 13) and digits.startswith("55"):
        return digits
    return ""
