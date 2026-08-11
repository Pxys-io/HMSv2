"""In-process SSE broadcaster (Plan/04 §4).

One process owns all streams in v1 (the production unit runs a single API
worker). Deltas are pushed to subscribers keyed by (doctor_id, date);
reconnecting clients refetch the snapshot first.
"""

import asyncio
import json
from collections import defaultdict
from datetime import date


class Broadcaster:
    def __init__(self) -> None:
        self._subs: dict[tuple[int, str], set[asyncio.Queue]] = defaultdict(set)

    def subscribe(self, key: tuple[int, str]) -> asyncio.Queue:
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._subs[key].add(queue)
        return queue

    def unsubscribe(self, key: tuple[int, str], queue: asyncio.Queue) -> None:
        self._subs[key].discard(queue)
        if not self._subs[key]:
            self._subs.pop(key, None)

    def publish(self, key: tuple[int, str], message: dict) -> None:
        payload = json.dumps(message, ensure_ascii=False)
        from contextlib import suppress

        for queue in list(self._subs.get(key, ())):
            with suppress(asyncio.QueueFull):
                # slow client: drop the delta, snapshot-on-connect heals it
                queue.put_nowait(payload)

    @staticmethod
    def key(doctor_id: int, target: date) -> tuple[int, str]:
        return (doctor_id, target.isoformat())


queue_broadcaster = Broadcaster()
