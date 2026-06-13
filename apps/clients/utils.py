import re


def normalize_phone(phone: str) -> str:
    cleaned = re.sub(r"[^\d+]", "", (phone or "").strip())

    if cleaned.startswith("00"):
        cleaned = f"+{cleaned[2:]}"

    if cleaned.startswith("8") and len(cleaned) == 11:
        cleaned = f"+7{cleaned[1:]}"

    if cleaned.startswith("+"):
        return cleaned

    return f"+{cleaned}" if cleaned else ""
