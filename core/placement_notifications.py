import asyncio
import logging

from fastapi import WebSocket

from repositories.student_placement_events import (
    get_latest_placement_event_id,
    list_unassigned_to_allocated_events_after,
)

logger = logging.getLogger(__name__)


class PlacementNotificationHub:
    def __init__(self, poll_interval_seconds: float = 2.0) -> None:
        self.poll_interval_seconds = poll_interval_seconds
        self._connections: set[WebSocket] = set()
        self._lock: asyncio.Lock | None = None
        self._stop_event: asyncio.Event | None = None
        self._task: asyncio.Task | None = None
        self._last_event_id = 0

    def _ensure_runtime_state(self) -> None:
        if self._lock is None:
            self._lock = asyncio.Lock()
        if self._stop_event is None:
            self._stop_event = asyncio.Event()

    async def connect(self, websocket: WebSocket) -> None:
        self._ensure_runtime_state()
        await websocket.accept()
        if self._lock is None:
            return
        async with self._lock:
            self._connections.add(websocket)

    async def disconnect(self, websocket: WebSocket) -> None:
        self._ensure_runtime_state()
        if self._lock is None:
            return
        async with self._lock:
            if websocket in self._connections:
                self._connections.remove(websocket)

    async def start(self) -> None:
        if self._task is not None and not self._task.done():
            return
        self._ensure_runtime_state()
        self._connections.clear()
        if self._stop_event is None:
            return
        self._stop_event.clear()
        self._last_event_id = await asyncio.to_thread(get_latest_placement_event_id)
        self._task = asyncio.create_task(self._run(), name="placement-notifier")
        logger.info(
            "Placement notifier started (last_event_id=%s)", self._last_event_id
        )

    async def stop(self) -> None:
        self._ensure_runtime_state()
        if self._stop_event is None:
            return
        self._stop_event.set()
        if self._task is None:
            return
        self._task.cancel()
        try:
            await self._task
        except asyncio.CancelledError:
            pass
        self._task = None
        self._connections.clear()
        self._lock = None
        self._stop_event = None
        logger.info("Placement notifier stopped")

    async def _run(self) -> None:
        self._ensure_runtime_state()
        if self._stop_event is None:
            return
        while not self._stop_event.is_set():
            try:
                events = await asyncio.to_thread(
                    list_unassigned_to_allocated_events_after,
                    self._last_event_id,
                    100,
                )
                for event in events:
                    self._last_event_id = max(self._last_event_id, event["event_id"])
                    await self.broadcast(
                        {
                            "type": "student_became_allocated",
                            "event": event,
                        }
                    )
            except Exception as exc:
                logger.warning("Placement notifier polling failed: %s", exc)

            try:
                await asyncio.wait_for(
                    self._stop_event.wait(), timeout=self.poll_interval_seconds
                )
            except asyncio.TimeoutError:
                pass

    async def broadcast(self, message: dict) -> None:
        self._ensure_runtime_state()
        if self._lock is None:
            return
        async with self._lock:
            sockets = list(self._connections)

        if len(sockets) == 0:
            return

        dead_sockets: list[WebSocket] = []
        for websocket in sockets:
            try:
                await websocket.send_json(message)
            except Exception:
                dead_sockets.append(websocket)

        if len(dead_sockets) > 0:
            async with self._lock:
                for websocket in dead_sockets:
                    if websocket in self._connections:
                        self._connections.remove(websocket)


placement_notification_hub = PlacementNotificationHub()
