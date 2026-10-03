from app.messaging.normalizer import normalize_phone_number, strip_channel_prefix


def format_whatsapp_address(phone_number: str) -> str:
    e164 = normalize_phone_number(strip_channel_prefix(phone_number))
    return f"whatsapp:{e164}"
