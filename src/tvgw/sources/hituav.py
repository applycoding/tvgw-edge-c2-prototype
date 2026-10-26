"""HIT-UAV COCO-style JSON parser with synthetic Calgary track GPS."""

from __future__ import annotations

import json
import math
import re
from datetime import datetime, timezone
from pathlib import Path

from tvgw.models import (
    Detection,
    FunctionalService,
    OperationalDomain,
    Priority,
)

CATEGORY_MAP = {
    0: "person",
    1: "car",
    2: "bicycle",
    3: "other_vehicle",
    4: "dontcare",
}

FILENAME_RE = re.compile(
    r"^(?P<a>\d+)_(?P<alt>\d+)_(?P<angle>\d+)_(?P<b>\d+)_(?P<frame>\d+)\.jpg$"
)

CALGARY_LAT = 51.04470
CALGARY_LON = -114.07190
BASE_GSD_M_PER_PX = 0.15


def _parse_filename(filename: str) -> float:
    m = FILENAME_RE.match(filename)
    if not m:
        return 60.0
    return float(m.group("alt"))


def _waypoint_for_image(image_id: int) -> tuple[float, float]:
    # Deterministic track: small circle around Calgary reference
    angle = (image_id % 360) * math.pi / 180.0
    lat = CALGARY_LAT + 0.01 * math.sin(angle)
    lon = CALGARY_LON + 0.01 * math.cos(angle)
    return lat, lon


def _offset_from_bbox(bbox: list[float], altitude_m: float) -> tuple[float, float]:
    x, y, w, h = bbox
    cx = x + w / 2.0
    cy = y + h / 2.0
    gsd = BASE_GSD_M_PER_PX * (altitude_m / 60.0)
    dx_m = (cx - 320.0) * gsd
    dy_m = (cy - 256.0) * gsd
    # crude meters to degrees at ~51N
    dlat = dy_m / 111_000.0
    dlon = dx_m / (111_000.0 * math.cos(math.radians(CALGARY_LAT)))
    return dlat, dlon


def load_hituav_json(
    path: Path,
    split: str,
    exclude_dontcare: bool = True,
) -> list[Detection]:
    data = json.loads(path.read_text(encoding="utf-8"))
    anns_key = "annotation" if "annotation" in data else "annotations"
    images = {img["id"]: img for img in data.get("images", [])}
    detections: list[Detection] = []
    for ann in data.get(anns_key, []):
        cat = ann.get("category_id", 4)
        if exclude_dontcare and cat == 4:
            continue
        obj_class = CATEGORY_MAP.get(cat, "other_vehicle")
        image_id = ann["image_id"]
        img = images.get(image_id)
        if not img:
            continue
        filename = img.get("filename", "")
        alt_m = _parse_filename(filename)
        base_lat, base_lon = _waypoint_for_image(image_id)
        dlat, dlon = _offset_from_bbox(ann.get("bbox", [0, 0, 0, 0]), alt_m)
        lat = base_lat + dlat
        lon = base_lon + dlon
        captured = img.get("date_captured", "2023-01-01T00:00:00")
        try:
            ts = datetime.fromisoformat(captured.replace("Z", "+00:00"))
            if ts.tzinfo is None:
                ts = ts.replace(tzinfo=timezone.utc)
            else:
                ts = ts.astimezone(timezone.utc)
        except ValueError:
            ts = datetime(2023, 1, 1, tzinfo=timezone.utc)

        ann_id = ann.get("id", 0)
        det_id = f"HITUAV_{image_id}_{ann_id}"
        priority = (
            Priority.P0_FLASH
            if obj_class == "person"
            else Priority.P1_IMMEDIATE
        )
        detections.append(
            Detection(
                detection_id=det_id,
                timestamp_utc=ts,
                source_sensor="HIT-UAV-IR",
                domain=OperationalDomain.AIR,
                functional_service=FunctionalService.INTEL,
                object_class=obj_class,
                confidence_score=0.92,
                latitude_deg=lat,
                longitude_deg=lon,
                priority=priority,
                altitude_m=alt_m,
                attributes={
                    "source_record_id": f"{split}:{image_id}:{ann_id}",
                    "orig_timestamp": captured,
                    "sim_gps": True,
                    "transform": "calgary_track_nominal_gsd_v1",
                },
            )
        )
    return detections


def load_all_hituav(raw_dir: Path, exclude_dontcare: bool = True) -> list[Detection]:
    out: list[Detection] = []
    for split, name in [("train", "train.json"), ("val", "val.json"), ("test", "test.json")]:
        path = raw_dir / name
        if path.is_file():
            out.extend(load_hituav_json(path, split, exclude_dontcare))
    return out
