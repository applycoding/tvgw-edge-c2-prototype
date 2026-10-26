import math
from datetime import datetime, timezone
from pathlib import Path

import pytest

from tvgw.models import (
    Detection,
    FunctionalService,
    OperationalDomain,
    Priority,
    ValidationError,
)
from tvgw.sources.firms import load_firms_detections
from tvgw.sources.hituav import load_hituav_json

ROOT = Path(__file__).resolve().parents[1]


def _base(**kwargs):
    defaults = {
        "detection_id": "HITUAV_1_1",
        "timestamp_utc": datetime(2026, 10, 26, 15, 40, tzinfo=timezone.utc),
        "source_sensor": "HIT-UAV-IR",
        "domain": OperationalDomain.AIR,
        "functional_service": FunctionalService.INTEL,
        "object_class": "person",
        "confidence_score": 0.92,
        "latitude_deg": 51.0447,
        "longitude_deg": -114.0719,
        "priority": Priority.P0_FLASH,
    }
    defaults.update(kwargs)
    return Detection(**defaults)


def test_rejects_nan_inf_and_bool():
    with pytest.raises(ValidationError):
        _base(latitude_deg=float("nan"))
    with pytest.raises(ValidationError):
        _base(confidence_score=True)
    with pytest.raises(ValidationError):
        _base(longitude_deg=float("inf"))


def test_confidence_bounds():
    with pytest.raises(ValidationError):
        _base(confidence_score=-0.01)
    with pytest.raises(ValidationError):
        _base(confidence_score=1.0001)


def test_enum_and_bounds():
    with pytest.raises(ValidationError):
        _base(domain="INVALID")
    d = _base(latitude_deg=90.0, longitude_deg=-180.0)
    assert d.latitude_deg == 90.0


def test_rounding_and_timestamp():
    d = _base(
        latitude_deg=51.044701234,
        longitude_deg=-114.071901234,
        confidence_score=0.92001,
        timestamp_utc=datetime(2026, 10, 26, 15, 40, 0, 500000, tzinfo=timezone.utc),
    )
    assert d.latitude_deg == 51.0447
    assert d.timestamp_utc.microsecond == 0


def test_naive_datetime_rejected():
    with pytest.raises(ValidationError):
        _base(timestamp_utc=datetime(2026, 1, 1))


def test_ncname_and_control_chars():
    with pytest.raises(ValidationError):
        _base(detection_id="9bad")
    with pytest.raises(ValidationError):
        _base(source_sensor="bad\x00sensor")


def test_attributes_limits():
    with pytest.raises(ValidationError):
        _base(attributes={str(i): "x" for i in range(17)})


def test_firms_time_parsing():
    csv = ROOT / "data/sample/firms_canada_24h_snapshot.csv"
    dets = load_firms_detections(csv, row_limit=3)
    assert dets
    assert dets[0].object_class == "fire_hotspot"


def test_hituav_singular_annotation_key():
    path = ROOT / "data/raw/hituav/train.json"
    dets = load_hituav_json(path, "train")
    assert len(dets) > 1000
    assert all(d.attributes.get("sim_gps") for d in dets[:5])


def test_hituav_excludes_dontcare():
    path = ROOT / "data/raw/hituav/train.json"
    dets = load_hituav_json(path, "train", exclude_dontcare=True)
    assert all(d.object_class != "dontcare" for d in dets)


def test_duplicate_id_suppression_in_corpus():
    from tvgw.corpus import build_full_corpus

    corpus = build_full_corpus(ROOT)
    ids = [d.detection_id for d in corpus]
    assert len(ids) == len(set(ids))


def test_firms_malformed_acq_time_defaults():
    import csv
    import tempfile

    with tempfile.NamedTemporaryFile("w", delete=False, suffix=".csv") as f:
        f.write("latitude,longitude,acq_date,acq_time,confidence\n")
        f.write("50,-100,2026-01-01,-5,l\n")
        f.write("50,-100,2026-01-01,2599,h\n")
        f.write("50,-100,2026-01-01,5,n\n")
        path = Path(f.name)
    dets = load_firms_detections(path)
    assert len(dets) == 3
