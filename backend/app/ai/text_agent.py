from __future__ import annotations

import logging

from openai import AsyncOpenAI

from app.config import Settings, get_settings
from app.messaging.schemas import TextAgentContext
from app.models import Contact, Conversation, Message

logger = logging.getLogger(__name__)

_SYSTEM_PROMPT = """You are a helpful business text agent for SMS and WhatsApp.
Keep replies concise and natural for messaging apps.
Respect the customer's preferred language when known.
Do not invent bookings, prices, inventory, or account actions.
If unsure, ask a short clarifying question.
"""


async def generate_text_agent_reply(
    *,
    contact: Contact,
    conversation: Conversation,
    incoming_message: Message,
    context: TextAgentContext | None = None,
    settings: Settings | None = None,
) -> str:
    """AI boundary for the text agent. Messaging code must not embed prompts."""
    resolved = settings or get_settings()
    if not resolved.openai_api_key:
        # Deterministic local fallback so infrastructure works without OpenAI.
        return _fallback_reply(contact=contact, incoming_message=incoming_message)

    agent_context = context or TextAgentContext(
        contact_id=contact.id,
        contact_name=contact.name,
        phone_number=contact.phone_number,
        preferred_language=contact.preferred_language.value,
        conversation_id=conversation.id,
        channel=conversation.channel,
        history=[],
        latest_user_message=incoming_message.body,
    )

    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {
            "role": "system",
            "content": (
                f"channel={agent_context.channel.value}; "
                f"preferred_language={agent_context.preferred_language}; "
                f"contact_name={agent_context.contact_name or 'unknown'}"
            ),
        },
    ]
    for item in agent_context.history[:-1]:
        role = item.role if item.role in {"user", "assistant", "system"} else "user"
        if item.role == "human":
            role = "assistant"
        messages.append({"role": role, "content": item.body})
    messages.append({"role": "user", "content": agent_context.latest_user_message})

    client = AsyncOpenAI(api_key=resolved.openai_api_key)
    response = await client.chat.completions.create(
        model=resolved.openai_text_model,
        messages=messages,
        temperature=0.4,
        max_tokens=400,
    )
    content = (response.choices[0].message.content or "").strip()
    if not content:
        raise RuntimeError("OpenAI returned an empty reply")
    return content


def _fallback_reply(*, contact: Contact, incoming_message: Message) -> str:
    name = contact.name or "there"
    language = contact.preferred_language.value
    if language == "roman_urdu":
        return f"Assalam o alaikum {name}! Aapka message mil gaya. Hum jald madad karte hain."
    if language == "urdu":
        return f"السلام علیکم {name}! آپ کا پیغام موصول ہو گیا۔ ہم جلد مدد کریں گے۔"
    return f"Hi {name}, thanks for your message. How can I help you today?"
