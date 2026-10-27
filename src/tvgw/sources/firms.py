"""NASA FIRMS VIIRS CSV reader."""

from __future__ import annotations

import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal, Never

from tvgw.models import (
    Detection,
    FunctionalService,
    OperationalDomain,
    Priority,
)

SensorIdFrom = Literal["constant", "satellite"]


def _parse_confidence(raw: str) -> float:
    raw = (raw or "").strip()
    if not raw:
        return 0.65
    lower = raw.lower()
    word_map = {
        "l": 0.30,
        "n": 0.65,
        "h": 0.90,
        "low": 0.30,
        "nominal": 0.65,
        "high": 0.90,
    }
    if lower in word_map:
        return word_map[lower]
    try:
        val = float(raw)
        return max(0.0, min(1.0, val / 100.0))
    except ValueError:
        return 0.65


def _parse_acq_time(raw: str) -> tuple[int, int, int]:
    raw = (raw or "").strip()
    if not raw or raw == "0":
        return 0, 0, 0
    try:
        if raw.lstrip("-").isdigit():
            v = int(raw)
            if v < 0:
                return 0, 5, 0
            if v > 2359:
                return 0, 5, 0
            hh = v // 100
            mm = v % 100
            if hh > 23 or mm > 59:
                return 0, 5, 0
            return hh, mm, 0
    except ValueError:
        pass
    return 0, 5, 0


def _parse_acq_date(raw: str) -> datetime:
    raw = (raw or "").strip()
    try:
        return datetime.strptime(raw, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError:
        return datetime(2026, 1, 1, tzinfo=timezone.utc)


def _source_sensor(row: dict[str, str], sensor_id_from: SensorIdFrom) -> str:
    if sensor_id_from == "constant":
        return "NASA-FIRMS-VIIRS"
    if sensor_id_from == "satellite":
        satellite = (row.get("satellite") or "").strip() or "UNKNOWN"
        return f"FIRMS-{satellite}"
    unexpected: Never = sensor_id_from
    raise ValueError(f"unknown sensor_id_from: {unexpected}")


def load_firms_detections(
    csv_path: Path,
    row_limit: int | None = None,
    sensor_id_from: SensorIdFrom = "constant",
) -> list[Detection]:
    detections: list[Detection] = []
    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for idx, row in enumerate(reader):
            if row_limit is not None and idx >= row_limit:
                break
            lat = float(row["latitude"])
            lon = float(row["longitude"])
            hh, mm, ss = _parse_acq_time(row.get("acq_time", ""))
            base = _parse_acq_date(row.get("acq_date", ""))
            ts = base.replace(hour=hh, minute=mm, second=ss)
            det_id = f"FIRMS_{row.get('acq_date', 'NA').replace('-', '')}_{idx:04d}"
            conf = _parse_confidence(row.get("confidence", ""))
            priority = Priority.P0_FLASH if conf >= 0.85 else Priority.P1_IMMEDIATE
            source_sensor = _source_sensor(row, sensor_id_from)
            detections.append(
                Detection(
                    detection_id=det_id,
                    timestamp_utc=ts,
                    source_sensor=source_sensor,
                    domain=OperationalDomain.SPACE,
                    functional_service=FunctionalService.INTEL,
                    object_class="fire_hotspot",
                    confidence_score=conf,
                    latitude_deg=lat,
                    longitude_deg=lon,
                    priority=priority,
                    altitude_m=None,
                    attributes={
                        "source_record_id": str(idx),
                        "frp": row.get("frp", ""),
                    },
                )
            )
    return detections
