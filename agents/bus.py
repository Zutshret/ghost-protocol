"""Message bus (B2).

InMemoryBus implements shared.types.BusAPI. The interface is deliberately tiny
(publish / subscribe) so an AGNTCY (A2A over SLIM) bus can replace it later.
Thread-safe: the incident engine runs in a worker thread while the FastAPI
websocket forwarder lives on the event loop.
"""

from __future__ import annotations

import asyncio
import threading
from typing import Callable

from shared.types import Message, MessageType

Handler = Callable[[Message], None]


class InMemoryBus:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._handlers: list[tuple[MessageType | None, Handler]] = []
        self._next_id = 1
        self.history: list[Message] = []

    def publish(self, message: Message) -> Message:
        with self._lock:
            message.id = self._next_id
            self._next_id += 1
            self.history.append(message)
            handlers = list(self._handlers)
        for topic, handler in handlers:
            if topic is None or topic == message.type:
                handler(message)
        return message

    def subscribe(self, handler: Handler, topic: MessageType | str | None = None) -> None:
        """Subscribe to every message, or only one MessageType (the 'topic')."""
        with self._lock:
            self._handlers.append((MessageType(topic) if topic else None, handler))


class WebSocketForwarder:
    """Bridges bus messages (any thread) to asyncio queues, one per websocket client."""

    def __init__(self, bus: InMemoryBus, loop: asyncio.AbstractEventLoop) -> None:
        self.loop = loop
        self.queues: set[asyncio.Queue] = set()
        bus.subscribe(self._on_message)

    def _on_message(self, message: Message) -> None:
        payload = message.model_dump(mode="json")
        for q in list(self.queues):
            self.loop.call_soon_threadsafe(q.put_nowait, payload)

    def add_client(self) -> asyncio.Queue:
        q: asyncio.Queue = asyncio.Queue()
        self.queues.add(q)
        return q

    def remove_client(self, q: asyncio.Queue) -> None:
        self.queues.discard(q)
