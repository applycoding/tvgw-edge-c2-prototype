from datetime import datetime, timezone

import pytest

from tvgw.mapping.text_report import detection_to_text_report, text_report_to_detection
from tvgw.models import Detection, FunctionalService, OperationalDomain, Priority, ValidationError


def _det():
    return Detection(
        detection_id="HITUAV_1_1",
        timestamp_utc=datetime(2026, 10, 26, 15, 40, tzinfo=timezone.utc),
        source_sensor="HIT/UAV",
        domain=OperationalDomain.AIR,
        functional_service=FunctionalService.INTEL,
        object_class="person",
        confidence_score=0.92,
        latitude_deg=51.0447,
        longitude_deg=-114.0719,
        priority=Priority.P0_FLASH,
        attributes={"note": "a;b|c%"},
    )


def test_percent_escape_order():
    text = detection_to_text_report(_det())
    assert "%2F" in text
    roundtrip = text_report_to_detection(text)
    assert roundtrip.source_sensor == "HIT/UAV"


def test_invalid_escape():
    bad = "MSGID/TVGW-SPOT-STANDIN/001/P0/EN//\nDTG/20260101T000000Z/SRC/x/DOM/AIR/SVC/INTEL//\nOBJ/PERSON/CONF/0.5/ID/HITUAV_1_1//\nLOC/1N/1E//\nRMK/%ZZ//\nENDAT//\n"
    with pytest.raises(ValidationError):
        text_report_to_detection(bad)


def test_class_casing():
    text = detection_to_text_report(_det())
    assert "OBJ/PERSON/" in text
    assert text_report_to_detection(text).object_class == "person"


def test_utf8_byte_length():
    d = _det()
    d = Detection(**{**d.__dict__, "source_sensor": "École"})
    text = detection_to_text_report(d)
    assert len(text.encode("utf-8")) > len(text)


def test_round_trip_core_fields():
    d = _det()
    back = text_report_to_detection(detection_to_text_report(d))
    assert back.detection_id == d.detection_id
    assert back.latitude_deg == d.latitude_deg


def test_msgid_priority():
    text = detection_to_text_report(_det())
    assert "/P0/" in text


def test_altitude_in_loc():
    d = Detection(**{**_det().__dict__, "altitude_m": 100.0})
    text = detection_to_text_report(d)
    assert "ALT/100.0M" in text


def test_endat_marker():
    assert detection_to_text_report(_det()).strip().endswith("ENDAT//")
