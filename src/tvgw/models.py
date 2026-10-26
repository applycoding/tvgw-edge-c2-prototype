"""Canonical Detection model with strict validation."""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from enum import IntEnum, StrEnum
from typing import Any

NCNAME_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.-]{0,63}$")
CONTROL_CHARS = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")


class Priority(IntEnum):
    P0_FLASH = 0
    P1_IMMEDIATE = 1
    P2_ROUTINE = 2


class OperationalDomain(StrEnum):
    LAND = "LAND"
    AIR = "AIR"
    MARITIME = "MARITIME"
    SPACE = "SPACE"
    CYBER = "CYBER"


class FunctionalService(StrEnum):
    C2 = "C2"
    INTEL = "INTEL"
    LOGISTICS = "LOGISTICS"


class ValidationError(ValueError):
    """Invalid Detection field."""


@dataclass(frozen=True)
class Detection:
    detection_id: str
    timestamp_utc: datetime
    source_sensor: str
    domain: OperationalDomain
    functional_service: FunctionalService
    object_class: str
    confidence_score: float
    latitude_deg: float
    longitude_deg: float
    priority: Priority
    altitude_m: float | None = None
    attributes: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        if not NCNAME_RE.match(self.detection_id):
            raise ValidationError(f"invalid NCName detection_id: {self.detection_id}")
        if CONTROL_CHARS.search(self.source_sensor):
            raise ValidationError("source_sensor contains control characters")
        if not self.source_sensor.strip():
            raise ValidationError("source_sensor empty")

        ts = self.timestamp_utc
        if ts.tzinfo is None:
            raise ValidationError("timestamp_utc must be timezone-aware")
        if ts.utcoffset() != timezone.utc.utcoffset(ts):
            raise ValidationError("timestamp_utc must be UTC")
        object.__setattr__(self, "timestamp_utc", ts.replace(microsecond=0))

        try:
            domain = OperationalDomain(self.domain)
            functional = FunctionalService(self.functional_service)
            priority = Priority(self.priority)
        except ValueError as exc:
            raise ValidationError(str(exc)) from exc
        object.__setattr__(self, "domain", domain)
        object.__setattr__(self, "functional_service", functional)
        object.__setattr__(self, "priority", priority)

        oc = self.object_class.strip().lower()
        if not oc or CONTROL_CHARS.search(oc):
            raise ValidationError("invalid object_class")
        object.__setattr__(self, "object_class", oc)

        conf = _finite_float(self.confidence_score, "confidence_score")
        if isinstance(self.confidence_score, bool):
            raise ValidationError("confidence_score cannot be bool")
        if not 0.0 <= conf <= 1.0:
            raise ValidationError("confidence_score out of range")
        object.__setattr__(self, "confidence_score", round(conf, 4))

        lat = _finite_float(self.latitude_deg, "latitude_deg")
        lon = _finite_float(self.longitude_deg, "longitude_deg")
        if isinstance(self.latitude_deg, bool) or isinstance(self.longitude_deg, bool):
            raise ValidationError("coordinates cannot be bool")
        if not -90.0 <= lat <= 90.0:
            raise ValidationError("latitude out of range")
        if not -180.0 <= lon <= 180.0:
            raise ValidationError("longitude out of range")
        if lat == 0.0:
            lat = 0.0  # normalize -0.0
        if lon == 0.0:
            lon = 0.0
        object.__setattr__(self, "latitude_deg", round(float(lat), 5))
        object.__setattr__(self, "longitude_deg", round(float(lon), 5))

        alt = self.altitude_m
        if alt is not None:
            if isinstance(alt, bool):
                raise ValidationError("altitude_m cannot be bool")
            alt_f = _finite_float(alt, "altitude_m")
            if not -500.0 <= alt_f <= 100000.0:
                raise ValidationError("altitude_m out of range")
            object.__setattr__(self, "altitude_m", round(alt_f, 1))

        attrs = _validate_attributes(self.attributes)
        object.__setattr__(self, "attributes", attrs)

    @property
    def priority_int(self) -> int:
        return int(self.priority)


def _finite_float(value: float, name: str) -> float:
    if isinstance(value, bool):
        raise ValidationError(f"{name} cannot be bool")
    try:
        f = float(value)
    except (TypeError, ValueError) as exc:
        raise ValidationError(f"{name} not numeric") from exc
    if f != f or f in (float("inf"), float("-inf")):
        raise ValidationError(f"{name} must be finite")
    return f


def _validate_attributes(attrs: dict[str, Any]) -> dict[str, Any]:
    if not isinstance(attrs, dict):
        raise ValidationError("attributes must be dict")
    if len(attrs) > 16:
        raise ValidationError("attributes too many keys")

    def depth(obj: Any, d: int = 0) -> int:
        if isinstance(obj, dict):
            if d > 2:
                return d
            return max((depth(v, d + 1) for v in obj.values()), default=d + 1)
        if isinstance(obj, list):
            return d + 1
        return d

    if depth(attrs) > 2:
        raise ValidationError("attributes nesting too deep")

    clean: dict[str, Any] = {}
    for k, v in attrs.items():
        if not isinstance(k, str) or len(k) > 256:
            raise ValidationError("attribute key invalid")
        if isinstance(v, str):
            if len(v) > 256 or CONTROL_CHARS.search(v):
                raise ValidationError("attribute string invalid")
        clean[k] = v
    return clean


def deadline_s(priority: Priority) -> float:
    return {Priority.P0_FLASH: 60.0, Priority.P1_IMMEDIATE: 300.0, Priority.P2_ROUTINE: 900.0}[
        priority
    ]
