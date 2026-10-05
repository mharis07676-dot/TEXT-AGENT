"""In-memory SSE fan-out for dashboard AI streaming.

ponytail: process-local hub; use Redis pub/sub if multiple API workers need shared streams.
"""

from __future__ import annotations

import asyncio
import logging
from collections import defaultdict
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)


class ConversationStreamHub:
    def __init__(self) -> None:
        self._subscribers: dict[UUID, set[asyncio.Queue[dict[str, Any] | None]]] = defaultdict(set)
        self._lock = asyncio.Lock()

    async def subscribe(self, conversation_id: UUID) -> asyncio.Queue[dict[str, Any] | None]:
        queue: asyncio.Queue[dict[str, Any] | None] = asyncio.Queue(maxsize=256)
        async with self._lock:
            self._subscribers[conversation_id].add(queue)
        return queue

    async def unsubscribe(
        self,
        conversation_id: UUID,
        queue: asyncio.Queue[dict[str, Any] | None],
    ) -> None:
        async with self._lock:
            subscribers = self._subscribers.get(conversation_id)
            if not subscribers:
                return
            subscribers.discard(queue)
            if not subscribers:
                self._subscribers.pop(conversation_id, None)

    async def publish(self, conversation_id: UUID, event: dict[str, Any]) -> None:
        async with self._lock:
            subscribers = list(self._subscribers.get(conversation_id, set()))
        for queue in subscribers:
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning(
                    "STREAM_QUEUE_FULL conversation_id=%s event=%s",
                    conversation_id,
                    event.get("type"),
                )

    async def publish_start(self, conversation_id: UUID, *, inbound_message_id: str) -> None:
        await self.publish(
            conversation_id,
            {"type": "start", "inbound_message_id": inbound_message_id},
        )

    async def publish_delta(self, conversation_id: UUID, *, text: str) -> None:
        await self.publish(conversation_id, {"type": "delta", "text": text})

    async def publish_done(
        self,
        conversation_id: UUID,
        *,
        message_id: str,
        body: str,
    ) -> None:
        await self.publish(
            conversation_id,
            {"type": "done", "message_id": message_id, "body": body},
        )

    async def publish_error(self, conversation_id: UUID, *, reason: str) -> None:
        await self.publish(conversation_id, {"type": "error", "reason": reason})

    async def publish_inbound(self, conversation_id: UUID, *, message: dict[str, Any]) -> None:
        await self.publish(conversation_id, {"type": "inbound", "message": message})


stream_hub = ConversationStreamHub()
