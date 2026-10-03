from __future__ import annotations

from app.config import Settings, get_settings
from app.messaging.providers.base import MessagingProvider
from app.messaging.providers.twilio_provider import TwilioMessagingProvider


def get_messaging_provider(settings: Settings | None = None) -> MessagingProvider:
    resolved = settings or get_settings()
    return TwilioMessagingProvider(resolved)
