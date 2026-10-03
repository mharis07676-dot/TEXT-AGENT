from app.messaging.normalizer import normalize_phone_number


def format_sms_address(phone_number: str) -> str:
    return normalize_phone_number(phone_number)
