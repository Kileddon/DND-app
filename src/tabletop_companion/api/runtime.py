from __future__ import annotations

import asyncio
import time
from collections import defaultdict, deque
from contextlib import suppress
from dataclasses import dataclass
from datetime import UTC, datetime
from threading import Lock

from fastapi import WebSocket

from tabletop_companion.application.event_contracts import serialize_event
from tabletop_companion.domain.access import DeviceRole, LocalDevice
from tabletop_companion.domain.errors import RateLimitError
from tabletop_companion.domain.events import DomainEvent


class SlidingWindowRateLimiter:
    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)
        self._lock = Lock()

    def check(self, key: str, *, limit: int, window_seconds: float) -> None:
        now = time.monotonic()
        threshold = now - window_seconds
        with self._lock:
            attempts = self._attempts[key]
            while attempts and attempts[0] <= threshold:
                attempts.popleft()
            if len(attempts) >= limit:
                raise RateLimitError(
                    "Too many attempts. Try again later.",
                    details={"retry_after_seconds": int(window_seconds)},
                )
            attempts.append(now)


class SafeErrorLog:
    """A bounded diagnostic log containing only timestamps and stable error codes."""

    def __init__(self, *, limit: int = 20) -> None:
        self._items: deque[dict[str, str]] = deque(maxlen=limit)
        self._lock = Lock()

    def record(self, code: str) -> None:
        item = {"occurred_at": datetime.now(UTC).isoformat(), "code": code}
        with self._lock:
            self._items.append(item)

    def snapshot(self) -> list[dict[str, str]]:
        with self._lock:
            return list(reversed(self._items))


@dataclass(eq=False, slots=True)
class LiveConnection:
    websocket: WebSocket
    device: LocalDevice
    queue: asyncio.Queue[dict[str, object]]
    connected_at: float
    last_cursor: int
    reconnecting: bool


class EventHub:
    def __init__(
        self, *, room_limit: int = 60, device_limit: int = 3, queue_size: int = 128
    ) -> None:
        self._room_limit = room_limit
        self._device_limit = device_limit
        self._queue_size = queue_size
        self._connections: set[LiveConnection] = set()
        self._lock = asyncio.Lock()

    async def connect(
        self, websocket: WebSocket, device: LocalDevice, *, last_cursor: int
    ) -> LiveConnection:
        async with self._lock:
            room_count = sum(
                connection.device.room_id == device.room_id for connection in self._connections
            )
            device_count = sum(
                connection.device.id == device.id for connection in self._connections
            )
            if room_count >= self._room_limit or device_count >= self._device_limit:
                raise RateLimitError("WebSocket connection limit was reached.")
            connection = LiveConnection(
                websocket=websocket,
                device=device,
                queue=asyncio.Queue(maxsize=self._queue_size),
                connected_at=time.monotonic(),
                last_cursor=last_cursor,
                reconnecting=last_cursor > 0,
            )
            self._connections.add(connection)
            return connection

    async def disconnect(self, connection: LiveConnection) -> None:
        async with self._lock:
            self._connections.discard(connection)

    async def disconnect_device(self, device_id: str) -> None:
        async with self._lock:
            targets = [item for item in self._connections if item.device.id == device_id]
            for target in targets:
                self._connections.discard(target)
        await asyncio.gather(
            *(target.websocket.close(code=4003, reason="device_revoked") for target in targets),
            return_exceptions=True,
        )

    async def publish(self, events: tuple[DomainEvent, ...]) -> None:
        if not events:
            return
        async with self._lock:
            connections = tuple(self._connections)
        overflowed: list[LiveConnection] = []
        for event in events:
            envelope = serialize_event(event)
            for connection in connections:
                if connection.device.room_id != event.room_id:
                    continue
                if event.visibility == "gm" and connection.device.role is not DeviceRole.GM:
                    continue
                try:
                    connection.queue.put_nowait(envelope)
                except asyncio.QueueFull:
                    overflowed.append(connection)
        for connection in set(overflowed):
            await self.disconnect(connection)
            with suppress(RuntimeError):
                await connection.websocket.close(code=1013, reason="backpressure")

    async def stats(self, room_id: str | None = None) -> dict[str, int]:
        async with self._lock:
            connections = tuple(self._connections)
        if room_id is not None:
            connections = tuple(item for item in connections if item.device.room_id == room_id)
        return {
            "connections": len(connections),
            "reconnecting": sum(item.reconnecting for item in connections),
        }

    async def device_presence(self, room_id: str) -> dict[str, dict[str, int | str]]:
        async with self._lock:
            connections = tuple(
                item for item in self._connections if item.device.room_id == room_id
            )
        result: dict[str, dict[str, int | str]] = {}
        for connection in connections:
            current = result.setdefault(
                connection.device.id,
                {"state": "online", "connections": 0},
            )
            current["connections"] = int(current["connections"]) + 1
            if connection.reconnecting:
                current["state"] = "reconnecting"
        return result
