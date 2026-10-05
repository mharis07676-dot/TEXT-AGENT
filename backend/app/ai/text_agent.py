from __future__ import annotations

import logging
import re
import time
from collections.abc import AsyncIterator, Callable, Awaitable
from typing import Any

from openai import AsyncOpenAI

from app.config import Settings, get_settings
from app.messaging.enums import MessagingChannel
from app.messaging.schemas import TextAgentContext
from app.models import Contact, Conversation, Message

logger = logging.getLogger(__name__)

HISTORY_LIMIT = 16
MAX_REPLY_TOKENS = 220

_SYSTEM_PROMPT = """You are a helpful business text agent for SMS and WhatsApp.

Identity & tone
- Talk like a real sales/support person: natural, brief, warm, professional — not corporate or robotic.
- Prefer 1–3 short sentences. Usually ask only ONE follow-up question.
- Acknowledge the customer's last answer before moving on.
- Match their tone (casual ↔ slightly more formal). Do not be stiff.

Conversation style
- Collect information gradually — one useful question at a time.
- Never dump a questionnaire (no “please provide type, location, budget, bedrooms…”).
- Do not restart the conversation or re-greet after the first exchange.
- Only greet on a brand-new conversation (or a clear “hi/hello” with no prior thread).
- Answer direct questions first, then ask a follow-up if needed.
- Do not repeat information the customer already gave.
- Do not repeat their name every message.
- Avoid filler like “Certainly”, “Thank you for your inquiry”, “How may I assist you today?”, “Please provide the following:” unless it truly fits.

Language
- Match the customer's latest meaningful message language.
- English → English. Roman Urdu → Roman Urdu. Urdu script → Urdu when practical.
- Mixed Urdu/English → keep the same mixed style. Do not randomly switch languages.

Memory
- Use the conversation history and known facts below. Never re-ask known details.
- If something is unclear, ask one short clarifying question.

Safety
- Do not invent prices, inventory, appointments, policies, or account actions.
- If you lack a fact: say you don't have it yet and offer to connect them with the team.
- Keep replies suitable for SMS/WhatsApp (no markdown walls, no long essays).
"""


DeltaCallback = Callable[[str], Awaitable[None]]


async def generate_text_agent_reply(
    *,
    contact: Contact,
    conversation: Conversation,
    incoming_message: Message,
    context: TextAgentContext | None = None,
    settings: Settings | None = None,
    on_delta: DeltaCallback | None = None,
) -> str:
    """Generate a full reply, optionally streaming deltas via on_delta."""
    full = ""
    async for delta in stream_text_agent_reply(
        contact=contact,
        conversation=conversation,
        incoming_message=incoming_message,
        context=context,
        settings=settings,
    ):
        full += delta
        if on_delta is not None:
            await on_delta(delta)
    return full.strip()


async def stream_text_agent_reply(
    *,
    contact: Contact,
    conversation: Conversation,
    incoming_message: Message,
    context: TextAgentContext | None = None,
    settings: Settings | None = None,
) -> AsyncIterator[str]:
    """Yield OpenAI text deltas. Accumulator is the caller's responsibility."""
    resolved = settings or get_settings()
    started = time.perf_counter()
    logger.info(
        "TEXT_AGENT_REQUEST_STARTED conversation_id=%s channel=%s model=%s",
        conversation.id,
        conversation.channel.value,
        resolved.openai_text_model,
    )

    if not resolved.openai_api_key:
        reply = _fallback_reply(contact=contact, incoming_message=incoming_message, context=context)
        yield reply
        logger.info(
            "TEXT_AGENT_GENERATION_COMPLETED conversation_id=%s ms=%d fallback=1",
            conversation.id,
            int((time.perf_counter() - started) * 1000),
        )
        return

    agent_context = context or TextAgentContext(
        contact_id=contact.id,
        contact_name=contact.name,
        phone_number=contact.phone_number,
        preferred_language=contact.preferred_language.value,
        conversation_id=conversation.id,
        channel=conversation.channel,
        history=[],
        latest_user_message=incoming_message.body,
        known_facts={},
        is_new_conversation=True,
    )

    messages = build_openai_messages(agent_context)
    client = AsyncOpenAI(api_key=resolved.openai_api_key)
    first_delta_logged = False
    openai_started = time.perf_counter()

    try:
        stream = await client.chat.completions.create(
            model=resolved.openai_text_model,
            messages=messages,
            temperature=0.5,
            max_tokens=MAX_REPLY_TOKENS,
            stream=True,
        )
        async for chunk in stream:
            choices = getattr(chunk, "choices", None) or []
            if not choices:
                continue
            delta = getattr(choices[0].delta, "content", None)
            if not delta:
                continue
            if not first_delta_logged:
                first_delta_logged = True
                logger.info(
                    "TEXT_AGENT_FIRST_DELTA conversation_id=%s ms=%d",
                    conversation.id,
                    int((time.perf_counter() - openai_started) * 1000),
                )
            yield delta
    except Exception:
        logger.exception(
            "TEXT_AGENT_STREAM_FAILED conversation_id=%s",
            conversation.id,
        )
        raise

    logger.info(
        "TEXT_AGENT_GENERATION_COMPLETED conversation_id=%s ms=%d first_delta=%s",
        conversation.id,
        int((time.perf_counter() - started) * 1000),
        int(first_delta_logged),
    )


def build_openai_messages(context: TextAgentContext) -> list[dict[str, str]]:
    """SYSTEM + context + recent history + latest user message (no duplicate latest)."""
    history = list(context.history)
    # Drop the trailing inbound copy of the latest user message if present.
    if history and history[-1].body.strip() == context.latest_user_message.strip():
        history = history[:-1]
    # Keep a bounded window.
    if len(history) > HISTORY_LIMIT:
        history = history[-HISTORY_LIMIT:]

    facts = context.known_facts or {}
    fact_lines = [f"- {key}: {value}" for key, value in facts.items() if value]
    facts_block = "\n".join(fact_lines) if fact_lines else "- (none yet)"

    greeting_rule = (
        "This is a new conversation — a short greeting is OK if natural."
        if context.is_new_conversation
        else "Conversation already started — do NOT greet again; continue naturally."
    )

    context_block = (
        f"Channel: {context.channel.value}\n"
        f"Preferred language hint: {context.preferred_language}\n"
        f"Contact name: {context.contact_name or 'unknown'}\n"
        f"{greeting_rule}\n"
        f"Known facts (do not re-ask):\n{facts_block}"
    )

    messages: list[dict[str, str]] = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "system", "content": context_block},
    ]

    for item in history:
        role = _map_history_role(item.role)
        body = (item.body or "").strip()
        if not body:
            continue
        messages.append({"role": role, "content": body})

    messages.append({"role": "user", "content": context.latest_user_message})
    return messages


def chunk_outbound_text(text: str, *, channel: MessagingChannel) -> list[str]:
    """Split long replies at sentence boundaries for SMS/WhatsApp. Never token-sized."""
    cleaned = " ".join((text or "").split()).strip()
    if not cleaned:
        return []

    max_chunks = 2 if channel is MessagingChannel.SMS else 3
    soft_limit = 280 if channel is MessagingChannel.SMS else 420
    if len(cleaned) <= soft_limit:
        return [cleaned]

    sentences = re.split(r"(?<=[.!?؟۔])\s+", cleaned)
    chunks: list[str] = []
    current = ""
    for sentence in sentences:
        sentence = sentence.strip()
        if not sentence:
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if current and len(candidate) > soft_limit and len(chunks) < max_chunks - 1:
            chunks.append(current)
            current = sentence
        else:
            current = candidate
    if current:
        chunks.append(current)

    if len(chunks) > max_chunks:
        head = chunks[: max_chunks - 1]
        tail = " ".join(chunks[max_chunks - 1 :])
        chunks = [*head, tail]
    return chunks[:max_chunks]


def merge_conversation_state(existing: dict[str, Any] | None, user_text: str) -> dict[str, Any]:
    """Lightweight heuristic state from user text. No extra AI call."""
    state = dict(existing or {})
    text = (user_text or "").strip()
    lower = text.lower()

    if any(w in lower for w in ("buy", "purchase", "kharid", "kharna", "ownership")):
        state.setdefault("intent", "buy")
    if any(w in lower for w in ("rent", "rental", "kiraya", "lease")):
        state.setdefault("intent", "rent")

    if any(w in lower for w in ("house", "ghar", "villa", "bungalow")):
        state.setdefault("property_type", "house")
    if any(w in lower for w in ("apartment", "flat", "condo", "studio")):
        state.setdefault("property_type", "apartment")
    if any(w in lower for w in ("plot", "land")):
        state.setdefault("property_type", "plot")

    budget = _extract_budget(text)
    if budget:
        state["budget"] = budget

    location = _extract_location(text)
    if location:
        state["location"] = location

    beds = _extract_bedrooms(lower)
    if beds:
        state["bedrooms"] = beds

    return {k: v for k, v in state.items() if v is not None and v != ""}


def build_known_facts(
    *,
    contact: Contact,
    conversation: Conversation,
    conversation_state: dict[str, Any] | None = None,
) -> dict[str, str]:
    facts: dict[str, str] = {}
    if contact.name:
        facts["contact_name"] = contact.name
    if contact.preferred_language and contact.preferred_language.value != "unknown":
        facts["preferred_language"] = contact.preferred_language.value

    meta = dict(contact.metadata_json or {})
    for key in ("lead_status", "notes"):
        value = meta.get(key)
        if value:
            facts[key] = str(value)
    tags = meta.get("tags")
    if isinstance(tags, list) and tags:
        facts["tags"] = ", ".join(str(t) for t in tags)

    state = conversation_state or (conversation.metadata_json or {}).get("conversation_state") or {}
    if isinstance(state, dict):
        for key, value in state.items():
            if value is not None and str(value).strip():
                facts[str(key)] = str(value)
    return facts


def _map_history_role(role: str) -> str:
    if role in {"user", "assistant", "system"}:
        return role
    if role == "human":
        return "assistant"
    return "user"


def _fallback_reply(
    *,
    contact: Contact,
    incoming_message: Message,
    context: TextAgentContext | None,
) -> str:
    language = contact.preferred_language.value
    is_new = context.is_new_conversation if context else True
    body = (incoming_message.body or "").lower()

    if language == "roman_urdu":
        if is_new and any(w in body for w in ("hi", "hello", "salam", "assalam")):
            return "Salam! Kaise madad kar sakta hoon?"
        return "Theek hai — thora aur batayein, aap kya dekh rahe hain?"
    if language == "urdu":
        if is_new:
            return "السلام علیکم! میں آپ کی کیسے مدد کر سکتا ہوں؟"
        return "ٹھیک ہے — تھوڑا اور بتائیں آپ کیا دیکھ رہے ہیں؟"

    if is_new and any(w in body for w in ("hi", "hello", "hey", "salam")):
        return "Hi! How can I help?"
    if "lahore" in body or "dha" in body or "property" in body or "house" in body:
        return "Sure. Are you looking to buy or rent?"
    return "Got it — what are you looking for?"


def _extract_budget(text: str) -> str | None:
    patterns = [
        r"(\d+(?:\.\d+)?\s*(?:crore|cr|lakh|lac|million|m))",
        r"(?:budget|under|around|about)\s*(?:of\s*)?(?:rs\.?|pkr)?\s*([\d,]+(?:\.\d+)?)",
    ]
    for pattern in patterns:
        match = re.search(pattern, text, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _extract_location(text: str) -> str | None:
    # Common PK areas; keep list small — history covers the rest.
    markers = [
        r"DHA(?:\s*Phase\s*\d+)?",
        r"Bahria(?:\s*Town)?",
        r"Gulberg(?:\s*[IVX\d]+)?",
        r"Johar Town",
        r"Model Town",
        r"Lahore",
        r"Islamabad",
        r"Karachi",
        r"Clifton",
    ]
    for marker in markers:
        match = re.search(marker, text, flags=re.IGNORECASE)
        if match:
            return match.group(0).strip()
    return None


def _extract_bedrooms(lower: str) -> str | None:
    match = re.search(r"(\d+)\s*(?:bed(?:room)?s?|br)\b", lower)
    if match:
        return match.group(1)
    return None
