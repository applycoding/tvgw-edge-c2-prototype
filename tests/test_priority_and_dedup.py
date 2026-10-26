from tvgw.models import Priority
from tvgw.priority import PriorityQueue, QueuedMessage, haversine_m


def _msg(pri: Priority, arrival: float, det_id: str):
    from datetime import datetime, timezone

    from tvgw.models import Detection, FunctionalService, OperationalDomain

    det = Detection(
        detection_id=det_id,
        timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_sensor="s",
        domain=OperationalDomain.AIR,
        functional_service=FunctionalService.INTEL,
        object_class="person",
        confidence_score=0.5,
        latitude_deg=0.0,
        longitude_deg=0.0,
        priority=pri,
    )
    return QueuedMessage(det, b"x", arrival, 0, "cbor")


def test_drop_incoming_when_all_p0():
    q = PriorityQueue(max_size=2)
    q.admit(_msg(Priority.P0_FLASH, 0.0, "a"))
    q.admit(_msg(Priority.P0_FLASH, 0.1, "b"))
    ok = q.admit(_msg(Priority.P0_FLASH, 0.2, "c"))
    assert not ok
    assert q.queue_drops_incoming[0] == 1


def test_evict_lower_priority():
    q = PriorityQueue(max_size=2)
    q.admit(_msg(Priority.P2_ROUTINE, 0.0, "p2"))
    q.admit(_msg(Priority.P2_ROUTINE, 0.1, "p2b"))
    assert q.admit(_msg(Priority.P0_FLASH, 0.2, "p0"))
    assert q.queue_evictions_by_priority[2] >= 1


def test_exact_duplicate_suppressed():
    q = PriorityQueue()
    assert q.admit(_msg(Priority.P1_IMMEDIATE, 0.0, "dup"))
    assert not q.admit(_msg(Priority.P1_IMMEDIATE, 0.1, "dup"))
    assert q.exact_id_duplicates_suppressed == 1


def test_priority_ordering():
    q = PriorityQueue(mode="priority")
    q.admit(_msg(Priority.P2_ROUTINE, 0.0, "a"))
    q.admit(_msg(Priority.P0_FLASH, 0.1, "b"))
    first = q.pop()
    assert first.detection.priority == Priority.P0_FLASH


def test_fifo_ordering():
    q = PriorityQueue(mode="fifo")
    q.admit(_msg(Priority.P0_FLASH, 0.2, "a"))
    q.admit(_msg(Priority.P2_ROUTINE, 0.1, "b"))
    first = q.pop()
    assert first is not None
    assert first.detection.detection_id == "b"
    assert first.arrival_time_s == 0.1


def test_antimeridian_distance():
    d = haversine_m(0.0, 179.9999, 0.0, -179.9999)
    assert 20 < d < 25


def test_expired_evicted():
    q = PriorityQueue()
    q.virtual_now = 1000.0
    q.admit(_msg(Priority.P0_FLASH, 0.0, "old"))
    q.pop()
    assert q.expired_in_queue[0] >= 1


def test_haversine_zero():
    assert haversine_m(1.0, 2.0, 1.0, 2.0) == 0.0
