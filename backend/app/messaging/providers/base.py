from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Mapping

from app.messaging.enums import MessagingChannel
from app.messaging.schemas import NormalizedInboundMessage, NormalizedStatusUpdate, OutboundSendResult


class MessagingProvider(ABC):
    """Provider interface so Twilio is not hardcoded throughout the app."""

    name: str

    @abstractmethod
    def validate_webhook(
        self,
        *,
        url: str,
        params: Mapping[str, Any],
        signature: str | None,
    ) -> bool:
        raise NotImplementedError

    @abstractmethod
    def extract_message_id(self, params: Mapping[str, Any]) -> str | None:
        raise NotImplementedError

    @abstractmethod
    def normalize_inbound(self, params: Mapping[str, Any]) -> NormalizedInboundMessage:
        raise NotImplementedError

    @abstractmethod
    def normalize_status(self, params: Mapping[str, Any]) -> NormalizedStatusUpdate:
        raise NotImplementedError

    @abstractmethod
    async def send_text(
        self,
        *,
        to_number: str,
        body: str,
        channel: MessagingChannel,
        status_callback_url: str | None = None,
    ) -> OutboundSendResult:
        raise NotImplementedError
