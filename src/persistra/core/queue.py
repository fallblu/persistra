from __future__ import annotations

import heapq
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from .events import Event


class EventQueue:
    """Priority queue ordered by (timestamp, priority), FIFO on ties."""

    def __init__(self) -> None:
        self._heap: list[tuple[Any, ...]] = []
        self._counter: int = 0

    def put(self, event: Event) -> None:
        """Add an event to the queue.

        Args:
            event: The event to enqueue.  Its position is determined by
                ``(timestamp, priority)`` with a FIFO tie-breaker.
        """
        heapq.heappush(self._heap, (event.timestamp, event.priority, self._counter, event))
        self._counter += 1

    def get(self) -> Event:
        """Remove and return the highest-priority event.

        Returns:
            The event with the earliest ``(timestamp, priority)`` key,
            with insertion order used to break ties.
        """
        _, _, _, event = heapq.heappop(self._heap)
        return event

    def peek(self) -> Event | None:
        """Return the highest-priority event without removing it.

        Returns:
            The next event that would be returned by :meth:`get`, or
            ``None`` if the queue is empty.
        """
        return self._heap[0][3] if self._heap else None

    def empty(self) -> bool:
        """Return ``True`` if the queue contains no events.

        Returns:
            ``True`` when the queue is empty, ``False`` otherwise.
        """
        return not self._heap

    def __len__(self) -> int:
        return len(self._heap)
