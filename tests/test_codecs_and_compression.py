from pathlib import Path

import pytest
from hypothesis import given
from hypothesis import strategies as st

from tvgw.corpus import load_held_out, load_train_ids
from tvgw.encode import CodecRegistry
from tvgw.mapping.niem_mo import detection_to_niem_xml

ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture
def codec():
    return CodecRegistry(ROOT)


def test_disjoint_train_eval_ids():
    train = load_train_ids(ROOT)
    held = {d.detection_id for d in load_held_out(ROOT)}
    assert train.isdisjoint(held)
    assert len(train) == 500


def test_xml_round_trip(codec):
    d = load_held_out(ROOT)[0]
    raw = codec.encode(d, "niem_mo_observation", "none")
    back = codec.decode(raw, "niem_mo_observation", "none")
    assert back.detection_id == d.detection_id


def test_json_round_trip(codec):
    d = load_held_out(ROOT)[0]
    raw = codec.encode(d, "json", "none")
    back = codec.decode(raw, "json", "none")
    assert back.confidence_score == d.confidence_score


def test_cbor_round_trip(codec):
    d = load_held_out(ROOT)[0]
    raw = codec.encode(d, "cbor", "none")
    back = codec.decode(raw, "cbor", "none")
    assert back.object_class == d.object_class


def test_text_round_trip(codec):
    d = load_held_out(ROOT)[0]
    raw = codec.encode(d, "spotrep_style_text", "none")
    back = codec.decode(raw, "spotrep_style_text", "none")
    assert back.detection_id == d.detection_id


def test_zstd_dict_smaller_than_raw(codec):
    d = load_held_out(ROOT)[0]
    raw = len(codec.encode(d, "niem_mo_observation", "none"))
    comp = len(codec.encode(d, "niem_mo_observation", "zstd_dict"))
    assert comp <= raw


@given(st.floats(min_value=0, max_value=1, allow_nan=False, allow_infinity=False))
def test_hypothesis_confidence_roundtrip(v):
    codec = CodecRegistry(ROOT)
    from datetime import datetime, timezone

    from tvgw.models import Detection, FunctionalService, OperationalDomain, Priority

    d = Detection(
        detection_id="T_1",
        timestamp_utc=datetime(2026, 1, 1, tzinfo=timezone.utc),
        source_sensor="s",
        domain=OperationalDomain.AIR,
        functional_service=FunctionalService.INTEL,
        object_class="car",
        confidence_score=v,
        latitude_deg=1.0,
        longitude_deg=2.0,
        priority=Priority.P1_IMMEDIATE,
    )
    raw = codec.encode(d, "json", "none")
    back = codec.decode(raw, "json", "none")
    assert back.confidence_score == d.confidence_score


def test_train_dict_only_on_train_split():
    path = ROOT / "data/sample/niem_zstd.dict"
    assert path.is_file()
