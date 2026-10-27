from datetime import datetime, timedelta, timezone

import pytest

from tvgw.associate import (
    AssociationWindows,
    associate_for_transmission,
    window_pair_counts,
    windows_from_config,
)
from tvgw.models import Detection, FunctionalService, OperationalDomain, Priority
from tvgw.priority import haversine_m


def _det(**overrides) -> Detection:
    fields = dict(
        detection_id="A_1",
        timestamp_utc=datetime(2026, 10, 25, 6, 50, tzinfo=timezone.utc),
        source_sensor="FIRMS-N20",
        domain=OperationalDomain.SPACE,
        functional_service=FunctionalService.INTEL,
        object_class="fire_hotspot",
        confidence_score=0.5,
        latitude_deg=48.0,
        longitude_deg=-64.0,
        priority=Priority.P1_IMMEDIATE,
        attributes={"source_record_id": "1"},
    )
    fields.update(overrides)
    return Detection(**fields)


def _windows(**overrides) -> AssociationWindows:
    fields = dict(max_distance_m=5000.0, max_time_s=3600.0, allow_cross_class=False)
    fields.update(overrides)
    return AssociationWindows(**fields)


def test_empty_and_singleton_are_unchanged():
    empty = associate_for_transmission([], _windows())
    assert empty.input_count == 0
    assert empty.output_count == 0
    assert empty.messages_saved == 0
    alone = _det()
    one = associate_for_transmission([alone], _windows())
    assert one.records[0] is alone
    assert "contributing_source_ids" not in one.records[0].attributes
    assert alone.attributes == {"source_record_id": "1"}


def test_same_sensor_does_not_merge():
    left = _det(detection_id="A_1", source_sensor="FIRMS-N20")
    right = _det(detection_id="A_2", source_sensor="FIRMS-N20", confidence_score=0.9)
    outcome = associate_for_transmission([right, left], _windows())
    assert outcome.output_count == 2
    assert outcome.merged_detection_count == 0
    assert outcome.multi_source_cluster_count == 0


def test_different_sensors_keep_highest_confidence_and_ids():
    low = _det(
        detection_id="LOW_1",
        source_sensor="FIRMS-N20",
        confidence_score=0.3,
        latitude_deg=48.0,
        priority=Priority.P0_FLASH,
    )
    high = _det(
        detection_id="HIGH_1",
        source_sensor="FIRMS-N21",
        confidence_score=0.95,
        latitude_deg=48.01,
        priority=Priority.P2_ROUTINE,
        timestamp_utc=datetime(2026, 10, 25, 7, 0, tzinfo=timezone.utc),
    )
    original_attrs = dict(high.attributes)
    outcome = associate_for_transmission([low, high], _windows())
    assert outcome.output_count == 1
    assert outcome.messages_saved == 1
    kept = outcome.records[0]
    assert kept.detection_id == "HIGH_1"
    assert kept.confidence_score == 0.95
    assert kept.latitude_deg == high.latitude_deg
    assert kept.priority == Priority.P0_FLASH
    assert kept.attributes["contributing_source_ids"] == ["HIGH_1", "LOW_1"]
    assert kept.attributes["contributing_sensors"] == ["FIRMS-N20", "FIRMS-N21"]
    assert high.attributes == original_attrs


def test_repeated_sensor_does_not_rejoin_a_mixed_cluster():
    start = datetime(2026, 10, 25, 6, 50, tzinfo=timezone.utc)
    first_s1 = _det(
        detection_id="S1_FIRST",
        source_sensor="S1",
        timestamp_utc=start,
        confidence_score=0.4,
    )
    s2 = _det(
        detection_id="S2_MID",
        source_sensor="S2",
        timestamp_utc=start + timedelta(seconds=1),
        confidence_score=0.8,
    )
    second_s1 = _det(
        detection_id="S1_AGAIN",
        source_sensor="S1",
        timestamp_utc=start + timedelta(seconds=2),
        confidence_score=0.99,
    )
    forward = associate_for_transmission([second_s1, first_s1, s2], _windows())
    backward = associate_for_transmission([s2, second_s1, first_s1], _windows())
    assert forward.output_count == backward.output_count == 2
    assert [record.detection_id for record in forward.records] == [
        record.detection_id for record in backward.records
    ]
    merged = next(record for record in forward.records if "contributing_source_ids" in record.attributes)
    alone = next(record for record in forward.records if "contributing_source_ids" not in record.attributes)
    assert merged.attributes["contributing_source_ids"] == ["S1_FIRST", "S2_MID"]
    assert merged.attributes["contributing_sensors"] == ["S1", "S2"]
    assert alone is second_s1
    assert alone.detection_id == "S1_AGAIN"
    assert "S1_AGAIN" not in merged.attributes["contributing_source_ids"]


def test_merged_priority_is_most_urgent():
    urgent = _det(
        detection_id="URGENT_LOW",
        source_sensor="SENSOR-A",
        confidence_score=0.2,
        latitude_deg=48.0,
        longitude_deg=-64.0,
        priority=Priority.P0_FLASH,
    )
    routine = _det(
        detection_id="ROUTINE_HIGH",
        source_sensor="SENSOR-B",
        confidence_score=0.99,
        latitude_deg=48.002,
        longitude_deg=-64.002,
        priority=Priority.P2_ROUTINE,
    )
    outcome = associate_for_transmission([routine, urgent], _windows())
    assert outcome.output_count == 1
    kept = outcome.records[0]
    assert kept.priority == Priority.P0_FLASH
    assert kept.confidence_score == 0.99
    assert kept.detection_id == "ROUTINE_HIGH"
    assert kept.latitude_deg == routine.latitude_deg
    assert kept.longitude_deg == routine.longitude_deg


def test_confidence_tie_uses_smallest_detection_id():
    first = _det(detection_id="M_2", source_sensor="SENSOR-A", confidence_score=0.5, latitude_deg=10.0)
    second = _det(detection_id="M_1", source_sensor="SENSOR-B", confidence_score=0.5, latitude_deg=10.5)
    outcome = associate_for_transmission([first, second], _windows())
    assert outcome.records[0].detection_id == "M_1"
    assert outcome.records[0].latitude_deg == 10.5


def test_different_class_blocked_unless_configured():
    person = _det(detection_id="P_1", source_sensor="CAM-A", object_class="person", confidence_score=0.4)
    car = _det(detection_id="C_1", source_sensor="CAM-B", object_class="car", confidence_score=0.8)
    blocked = associate_for_transmission([person, car], _windows())
    assert blocked.output_count == 2
    allowed = associate_for_transmission([person, car], _windows(allow_cross_class=True))
    assert allowed.output_count == 1
    assert allowed.records[0].object_class == "car"
    assert allowed.records[0].detection_id == "C_1"


def test_distance_and_time_boundaries_are_inclusive():
    origin = _det(detection_id="ORIG", source_sensor="SENSOR-A", longitude_deg=0.0, latitude_deg=0.0)
    other = _det(detection_id="OTHER", source_sensor="SENSOR-B", longitude_deg=0.02, latitude_deg=0.0)
    distance = haversine_m(0.0, 0.0, 0.0, 0.02)
    assert associate_for_transmission([origin, other], _windows(max_distance_m=distance)).output_count == 1
    assert associate_for_transmission([origin, other], _windows(max_distance_m=distance - 1)).output_count == 2
    later = _det(
        detection_id="LATER",
        source_sensor="SENSOR-B",
        latitude_deg=origin.latitude_deg,
        longitude_deg=origin.longitude_deg,
        timestamp_utc=origin.timestamp_utc + timedelta(seconds=1800),
    )
    assert associate_for_transmission([origin, later], _windows(max_time_s=1800)).output_count == 1
    assert associate_for_transmission([origin, later], _windows(max_time_s=1799)).output_count == 2


def test_anchor_not_member_distance_and_order_independence():
    anchor = _det(detection_id="ANCHOR", source_sensor="SENSOR-A", confidence_score=0.9, longitude_deg=0.0)
    near = _det(detection_id="NEAR", source_sensor="SENSOR-B", confidence_score=0.2, longitude_deg=0.02)
    far = _det(detection_id="FAR", source_sensor="SENSOR-C", confidence_score=0.2, longitude_deg=0.05)
    distance_far = haversine_m(anchor.latitude_deg, 0.0, anchor.latitude_deg, 0.05)
    distance_near = haversine_m(anchor.latitude_deg, 0.0, anchor.latitude_deg, 0.02)
    windows = _windows(max_distance_m=(distance_near + distance_far) / 2)
    forward = associate_for_transmission([far, anchor, near], windows)
    backward = associate_for_transmission([near, far, anchor], windows)
    assert forward.output_count == backward.output_count == 2
    kept_ids = [record.detection_id for record in forward.records]
    assert kept_ids == [record.detection_id for record in backward.records]
    merged = next(record for record in forward.records if record.detection_id == "ANCHOR")
    assert merged.attributes["contributing_source_ids"] == ["ANCHOR", "NEAR"]
    assert any(record.detection_id == "FAR" for record in forward.records)


def test_antimeridian_and_duplicate_ids():
    east = _det(detection_id="EAST", source_sensor="SENSOR-A", latitude_deg=0.0, longitude_deg=179.999)
    west = _det(detection_id="WEST", source_sensor="SENSOR-B", latitude_deg=0.0, longitude_deg=-179.999)
    outcome = associate_for_transmission([east, west], _windows(max_distance_m=1000))
    assert outcome.output_count == 1
    dup_a = _det(detection_id="SAME", source_sensor="SENSOR-A")
    dup_b = _det(detection_id="SAME", source_sensor="SENSOR-B", confidence_score=0.2)
    dup = associate_for_transmission([dup_a, dup_b], _windows())
    assert dup.output_count == 1
    assert dup.records[0].attributes["contributing_source_ids"] == ["SAME"]
    assert dup.messages_saved == 1


def test_negative_windows_rejected():
    with pytest.raises(ValueError):
        AssociationWindows(max_distance_m=-1, max_time_s=1)
    with pytest.raises(ValueError):
        AssociationWindows(max_distance_m=1, max_time_s=float("nan"))
    with pytest.raises(ValueError):
        windows_from_config({"association": {"allow_cross_class": "false"}})


def test_pair_counts_do_not_merge():
    same = [
        _det(detection_id="S1", source_sensor="SENSOR-A"),
        _det(detection_id="S2", source_sensor="SENSOR-A", longitude_deg=-64.01),
    ]
    counts = window_pair_counts(same, _windows())
    assert counts["same_sensor_same_class"] == 1
    assert counts["different_sensor_same_class"] == 0
    mixed = same + [_det(detection_id="D1", source_sensor="SENSOR-B", object_class="car")]
    mixed_counts = window_pair_counts(mixed, _windows())
    assert mixed_counts["different_class"] == 2
