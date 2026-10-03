from __future__ import annotations

import re

import phonenumbers
from phonenumbers import NumberParseException

from app.messaging.enums import MessagingChannel

_WHATSAPP_PREFIX = "whatsapp:"
_NON_DIGIT_PLUS = re.compile(r"[^\d+]")


def strip_channel_prefix(value: str) -> str:
    raw = (value or "").strip()
    if raw.lower().startswith(_WHATSAPP_PREFIX):
        return raw[len(_WHATSAPP_PREFIX) :].strip()
    return raw


def detect_channel(from_value: str = "", to_value: str = "") -> MessagingChannel:
    combined = f"{from_value} {to_value}".lower()
    if _WHATSAPP_PREFIX in combined:
        return MessagingChannel.WHATSAPP
    return MessagingChannel.SMS


def normalize_phone_number(value: str, *, default_region: str = "PK") -> str:
    """Normalize to E.164 where practical; otherwise return a cleaned fallback."""
    cleaned = strip_channel_prefix(value)
    cleaned = _NON_DIGIT_PLUS.sub("", cleaned)
    if not cleaned:
        return ""

    try:
        parsed = phonenumbers.parse(cleaned, default_region if not cleaned.startswith("+") else None)
        if phonenumbers.is_possible_number(parsed):
            return phonenumbers.format_number(parsed, phonenumbers.PhoneNumberFormat.E164)
    except NumberParseException:
        pass

    digits = re.sub(r"\D", "", cleaned)
    if cleaned.startswith("+"):
        return f"+{digits}"
    if digits:
        return f"+{digits}"
    return cleaned
