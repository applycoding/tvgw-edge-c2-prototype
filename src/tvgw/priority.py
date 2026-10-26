"""Priority scoring, deduplication, and bounded queue."""

from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import Deque, Literal

from tvgw.models import Detection, Priority, deadline_s

SchedulingMode = Literal["priority", "fifo"]


@dataclass
class QueuedMessage:
    detection: Detection
    payload: bytes
    arrival_time_s: float
    enqueue_seq: int
    profile: str

    @property
    def priority_int(self) -> int:
        return int(self.detection.priority)


@dataclass
class PriorityQueue:
    mode: SchedulingMode = "priority"
    max_size: int = 100
    virtual_now: float = 0.0
    queue: Deque[QueuedMessage] = field(default_factory=deque)
    enqueue_seq: int = 0
    seen_ids: set[str] = field(default_factory=set)
    exact_id_duplicates_suppressed: int = 0
    expired_in_queue: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    queue_evictions_by_priority: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    queue_drops_incoming: dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})

    def admit(self, msg: QueuedMessage) -> bool:
        if msg.detection.detection_id in self.seen_ids:
            self.exact_id_duplicates_suppressed += 1
            return False
        self._evict_expired()
        if len(self.queue) >= self.max_size:
            victim_idx = self._find_victim(msg.priority_int)
            if victim_idx is None:
                self.queue_drops_incoming[msg.priority_int] += 1
                return False
            victim = self.queue[victim_idx]
            del self.queue[victim_idx]
            self.queue_evictions_by_priority[victim.priority_int] += 1
        self.enqueue_seq += 1
        msg.enqueue_seq = self.enqueue_seq
        self.queue.append(msg)
        self.seen_ids.add(msg.detection.detection_id)
        self._sort()
        return True

    def pop(self) -> QueuedMessage | None:
        self._evict_expired()
        if not self.queue:
            return None
        return self.queue.popleft()

    def _evict_expired(self) -> None:
        keep: Deque[QueuedMessage] = deque()
        while self.queue:
            m = self.queue.popleft()
            age = self.virtual_now - m.arrival_time_s
            if age > deadline_s(m.detection.priority):
                self.expired_in_queue[m.priority_int] += 1
            else:
                keep.append(m)
        self.queue = keep

    def _find_victim(self, incoming_pri: int) -> int | None:
        for i, m in enumerate(self.queue):
            if m.priority_int > incoming_pri:
                return i
        return None

    def _sort(self) -> None:
        items = list(self.queue)
        if self.mode == "fifo":
            items.sort(key=lambda m: (m.arrival_time_s, m.enqueue_seq))
        else:
            items.sort(key=lambda m: (m.priority_int, m.arrival_time_s, m.enqueue_seq))
        self.queue = deque(items)


class RuleBasedPriorityScorer:
    def score(self, det: Detection) -> Priority:
        return det.priority


def haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    r = 6371000.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))
