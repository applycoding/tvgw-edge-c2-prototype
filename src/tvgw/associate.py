"""Rule-based cross-source association applied before transmission.

Detections merge only when their sensors differ, they fall inside the
configured distance and time windows of the cluster anchor, and their object
classes match (unless cross-class merges are configured). The kept record is
the highest-confidence contributor. Ties keep the smallest detection id.
This step does not score whether a detection was correct.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from tvgw.models import Detection
from tvgw.priority import haversine_m


@dataclass(frozen=True)
class AssociationWindows:
    max_distance_m: float
    max_time_s: float
    allow_cross_class: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.allow_cross_class, bool):
            raise ValueError("allow_cross_class must be a bool")
        for name, value in (
            ("max_distance_m", self.max_distance_m),
            ("max_time_s", self.max_time_s),
        ):
            try:
                number = float(value)
            except (TypeError, ValueError) as exc:
                raise ValueError(f"{name} must be a number") from exc
            if not math.isfinite(number) or number < 0:
                raise ValueError(f"{name} must be finite and non-negative")


def windows_from_config(cfg: dict) -> AssociationWindows:
    block = cfg.get("association") or {}
    allow = block.get("allow_cross_class", False)
    if not isinstance(allow, bool):
        raise ValueError("association.allow_cross_class must be a boolean")
    return AssociationWindows(
        max_distance_m=float(block.get("max_distance_m", 1000.0)),
        max_time_s=float(block.get("max_time_s", 1800.0)),
        allow_cross_class=allow,
    )


@dataclass
class AssociationOutcome:
    records: tuple[Detection, ...]
    input_count: int
    output_count: int
    merged_detection_count: int
    multi_source_cluster_count: int

    @property
    def messages_saved(self) -> int:
        return self.merged_detection_count


@dataclass
class _Cluster:
    members: list[Detection] = field(default_factory=list)

    def anchor(self) -> Detection:
        return min(self.members, key=lambda det: (-det.confidence_score, det.detection_id))


def _time_delta_s(left: Detection, right: Detection) -> float:
    return abs((left.timestamp_utc - right.timestamp_utc).total_seconds())


def _cross_source(det: Detection, cluster: _Cluster) -> bool:
    return any(member.source_sensor != det.source_sensor for member in cluster.members)


def _class_compatible(det: Detection, cluster: _Cluster, allow_cross_class: bool) -> bool:
    if allow_cross_class:
        return True
    return all(member.object_class == det.object_class for member in cluster.members)


def _emit(cluster: _Cluster) -> Detection:
    if len(cluster.members) == 1:
        return cluster.members[0]
    anchor = cluster.anchor()
    ids = sorted({member.detection_id for member in cluster.members})
    sensors = sorted({member.source_sensor for member in cluster.members})
    attributes = dict(anchor.attributes)
    attributes["contributing_source_ids"] = ids
    attributes["contributing_sensors"] = sensors
    return Detection(
        detection_id=anchor.detection_id,
        timestamp_utc=anchor.timestamp_utc,
        source_sensor=anchor.source_sensor,
        domain=anchor.domain,
        functional_service=anchor.functional_service,
        object_class=anchor.object_class,
        confidence_score=max(member.confidence_score for member in cluster.members),
        latitude_deg=anchor.latitude_deg,
        longitude_deg=anchor.longitude_deg,
        priority=anchor.priority,
        altitude_m=anchor.altitude_m,
        attributes=attributes,
    )


def associate_for_transmission(
    detections: list[Detection],
    windows: AssociationWindows,
) -> AssociationOutcome:
    """Return the records that would be transmitted after association.

    A detection joins at most one existing cluster. The comparison is against
    that cluster's anchor (highest confidence, then smallest detection id),
    not against every member. Input order does not matter: candidates are
    processed by timestamp, detection id, then sensor.
    """
    ordered = sorted(
        detections,
        key=lambda det: (det.timestamp_utc, det.detection_id, det.source_sensor),
    )
    clusters: list[_Cluster] = []
    for det in ordered:
        best_index: int | None = None
        best_key: tuple[float, float, str, int] | None = None
        for index, cluster in enumerate(clusters):
            if not _class_compatible(det, cluster, windows.allow_cross_class):
                continue
            if not _cross_source(det, cluster):
                continue
            anchor = cluster.anchor()
            distance_m = haversine_m(
                det.latitude_deg,
                det.longitude_deg,
                anchor.latitude_deg,
                anchor.longitude_deg,
            )
            delta_s = _time_delta_s(det, anchor)
            if distance_m > windows.max_distance_m or delta_s > windows.max_time_s:
                continue
            key = (distance_m, delta_s, anchor.detection_id, index)
            if best_key is None or key < best_key:
                best_key = key
                best_index = index
        if best_index is None:
            clusters.append(_Cluster([det]))
        else:
            clusters[best_index].members.append(det)

    records = tuple(sorted((_emit(cluster) for cluster in clusters), key=lambda det: det.detection_id))
    multi = sum(1 for cluster in clusters if len(cluster.members) > 1)
    output_count = len(records)
    input_count = len(detections)
    return AssociationOutcome(
        records=records,
        input_count=input_count,
        output_count=output_count,
        merged_detection_count=input_count - output_count,
        multi_source_cluster_count=multi,
    )


def window_pair_counts(detections: list[Detection], windows: AssociationWindows) -> dict[str, int]:
    """Count unordered pairs inside the windows, without merging them."""
    same_sensor_same_class = 0
    different_sensor_same_class = 0
    different_class = 0
    ordered = list(detections)
    for left_index, left in enumerate(ordered):
        for right in ordered[left_index + 1 :]:
            if _time_delta_s(left, right) > windows.max_time_s:
                continue
            distance_m = haversine_m(
                left.latitude_deg,
                left.longitude_deg,
                right.latitude_deg,
                right.longitude_deg,
            )
            if distance_m > windows.max_distance_m:
                continue
            if left.object_class != right.object_class:
                different_class += 1
            elif left.source_sensor == right.source_sensor:
                same_sensor_same_class += 1
            else:
                different_sensor_same_class += 1
    return {
        "same_sensor_same_class": same_sensor_same_class,
        "different_sensor_same_class": different_sensor_same_class,
        "different_class": different_class,
    }
