from __future__ import annotations

import asyncio
import logging
from typing import Any, Mapping, Never

from twilio.request_validator import RequestValidator
from twilio.rest import Client

from app.config import Settings
from app.messaging.enums import MessagingChannel, MessagingProviderName
from app.messaging.normalizer import detect_channel, normalize_phone_number, strip_channel_prefix
from app.messaging.providers.base import MessagingProvider
from app.messaging.schemas import NormalizedInboundMessage, NormalizedStatusUpdate, OutboundSendResult

logger = logging.getLogger(__name__)


class TwilioSendError(RuntimeError):
    pass


class TwilioMessagingProvider(MessagingProvider):
    name = MessagingProviderName.TWILIO.value

    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._validator = RequestValidator(settings.twilio_auth_token) if settings.twilio_auth_token else None
        self._client: Client | None = None
        if settings.twilio_account_sid and settings.twilio_auth_token:
            self._client = Client(settings.twilio_account_sid, settings.twilio_auth_token)

    def validate_webhook(
        self,
        *,
        url: str,
        params: Mapping[str, Any],
        signature: str | None,
    ) -> bool:
        if self._settings.app_env.lower() == "development" and not self._settings.twilio_auth_token:
            # Local tests without Twilio credentials.
            return True
        if not self._validator or not signature:
            return False
        form = {str(k): "" if v is None else str(v) for k, v in params.items()}
        return bool(self._validator.validate(url, form, signature))

    def extract_message_id(self, params: Mapping[str, Any]) -> str | None:
        sid = params.get("MessageSid") or params.get("SmsSid")
        if sid is None:
            return None
        value = str(sid).strip()
        return value or None

    def normalize_inbound(self, params: Mapping[str, Any]) -> NormalizedInboundMessage:
        message_id = self.extract_message_id(params)
        if not message_id:
            raise ValueError("Missing Twilio message SID")

        from_raw = str(params.get("From") or "").strip()
        to_raw = str(params.get("To") or "").strip()
        if not from_raw:
            raise ValueError("Missing sender")

        channel = detect_channel(from_raw, to_raw)
        text = str(params.get("Body") or "")
        media_urls = _extract_media_urls(params)

        return NormalizedInboundMessage(
            provider=MessagingProviderName.TWILIO,
            channel=channel,
            message_id=message_id,
            from_number=normalize_phone_number(from_raw),
            to_number=normalize_phone_number(to_raw),
            text=text,
            media_urls=media_urls,
            raw_metadata={
                "AccountSid": params.get("AccountSid"),
                "MessagingServiceSid": params.get("MessagingServiceSid"),
                "NumMedia": params.get("NumMedia"),
                "SmsStatus": params.get("SmsStatus"),
                "FromCity": params.get("FromCity"),
                "FromCountry": params.get("FromCountry"),
                "raw_from": from_raw,
                "raw_to": to_raw,
            },
        )

    def normalize_status(self, params: Mapping[str, Any]) -> NormalizedStatusUpdate:
        message_id = self.extract_message_id(params)
        if not message_id:
            raise ValueError("Missing Twilio message SID")

        status = str(params.get("MessageStatus") or params.get("SmsStatus") or "").strip()
        if not status:
            raise ValueError("Missing Twilio message status")

        from_raw = str(params.get("From") or "")
        to_raw = str(params.get("To") or "")
        channel: MessagingChannel | None = None
        if from_raw or to_raw:
            channel = detect_channel(from_raw, to_raw)

        error_code = params.get("ErrorCode")
        return NormalizedStatusUpdate(
            provider=MessagingProviderName.TWILIO,
            message_id=message_id,
            status=status,
            channel=channel,
            error_code=None if error_code is None else str(error_code),
            raw_metadata={
                "AccountSid": params.get("AccountSid"),
                "ErrorMessage": params.get("ErrorMessage"),
            },
        )

    async def send_text(
        self,
        *,
        to_number: str,
        body: str,
        channel: MessagingChannel,
        status_callback_url: str | None = None,
    ) -> OutboundSendResult:
        if self._client is None:
            raise TwilioSendError("Twilio client is not configured")

        from_number = self._from_for_channel(channel)
        if not from_number:
            raise TwilioSendError(f"No Twilio sender configured for channel={channel.value}")

        to_address = self._address_for_channel(to_number, channel)
        create_kwargs: dict[str, Any] = {
            "to": to_address,
            "from_": from_number,
            "body": body,
        }
        if status_callback_url:
            create_kwargs["status_callback"] = status_callback_url

        try:
            # Twilio REST client is synchronous — keep the event loop free.
            message = await asyncio.to_thread(self._client.messages.create, **create_kwargs)
        except Exception as exc:  # noqa: BLE001 — surface provider failures cleanly
            logger.exception(
                "OUTBOUND_MESSAGE_FAILED provider=twilio channel=%s",
                channel.value,
            )
            raise TwilioSendError(str(exc)) from exc

        return OutboundSendResult(
            provider_message_sid=str(message.sid),
            provider_status=getattr(message, "status", None),
            channel=channel,
        )

    def _from_for_channel(self, channel: MessagingChannel) -> str:
        if channel is MessagingChannel.SMS:
            return self._settings.twilio_sms_from_number
        if channel is MessagingChannel.WHATSAPP:
            value = self._settings.twilio_whatsapp_from
            if value and not value.lower().startswith("whatsapp:"):
                return f"whatsapp:{strip_channel_prefix(value)}"
            return value
        _assert_never(channel)

    @staticmethod
    def _address_for_channel(number: str, channel: MessagingChannel) -> str:
        e164 = normalize_phone_number(number)
        if channel is MessagingChannel.WHATSAPP:
            return f"whatsapp:{e164}"
        if channel is MessagingChannel.SMS:
            return e164
        _assert_never(channel)


def _assert_never(value: Never) -> Never:
    raise TwilioSendError(f"Unsupported channel: {value}")


def _extract_media_urls(params: Mapping[str, Any]) -> list[str]:
    try:
        count = int(params.get("NumMedia") or 0)
    except (TypeError, ValueError):
        count = 0
    urls: list[str] = []
    for index in range(count):
        url = params.get(f"MediaUrl{index}")
        if url:
            urls.append(str(url))
    return urls
