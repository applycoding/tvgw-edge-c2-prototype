from datetime import datetime, timezone

import pytest

from tvgw.mapping.text_report import detection_to_text_report, text_report_to_detection
from tvgw.messages import translate
from tvgw.models import Detection, FunctionalService, OperationalDomain, Priority, ValidationError


def _det(**overrides):
    fields = dict(
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
    fields.update(overrides)
    return Detection(**fields)


ENGLISH = (
    "MSGID/TVGW-SPOT-STANDIN/001/P0/EN//\n"
    "DTG/20261026T154000Z/SRC/HIT%2FUAV/DOM/AIR/SVC/INTEL//\n"
    "OBJ/PERSON/CONF/0.9200/ID/HITUAV_1_1//\n"
    "LOC/51.04470N/114.07190W//\n"
    "RMK/note=a%3Bb%7Cc%25//\n"
    "ENDAT//\n"
)

FRENCH = (
    "IDMSG/TVGW-SPOT-PROVISOIRE/001/P0/FR//\n"
    "GDH/20261026T154000Z/SRE/HIT%2FUAV/DMN/AIR/SRV/INTEL//\n"
    "CBL/PERSON/NCF/0.9200/IDE/HITUAV_1_1//\n"
    "LIE/51.04470N/114.07190W//\n"
    "REM/note=a%3Bb%7Cc%25//\n"
    "FIN//\n"
)


def test_english_report_matches_historical_labels():
    assert detection_to_text_report(_det(), lang="en") == ENGLISH
    assert detection_to_text_report(_det()) == ENGLISH


def test_french_report_uses_catalog_labels():
    text = detection_to_text_report(_det(), lang="fr")
    assert text == FRENCH
    assert "MSGID/" not in text
    assert "ENDAT" not in text


def test_round_trip_preserves_priority_and_remark():
    original = _det()
    for lang in ("en", "fr"):
        back = text_report_to_detection(detection_to_text_report(original, lang=lang))
        assert back.priority == Priority.P0_FLASH
        assert back.attributes["note"] == "a;b|c%"
        assert back.source_sensor == "HIT/UAV"
        assert back.detection_id == original.detection_id
        assert back.object_class == "person"


def test_french_altitude_token():
    det = _det(altitude_m=100.0, attributes={})
    text = detection_to_text_report(det, lang="fr")
    assert "/ALTI/100.0M" in text
    assert text_report_to_detection(text).altitude_m == 100.0


def test_malformed_escape_uses_language_of_the_report():
    french = (
        "IDMSG/TVGW-SPOT-PROVISOIRE/001/P0/FR//\n"
        "GDH/20260101T000000Z/SRE/x/DMN/AIR/SRV/INTEL//\n"
        "CBL/PERSON/NCF/0.5/IDE/HITUAV_1_1//\n"
        "LIE/1.00000N/1.00000E//\n"
        "REM/%ZZ//\n"
        "FIN//\n"
    )
    with pytest.raises(ValidationError) as caught:
        text_report_to_detection(french)
    assert str(caught.value) == translate("fr", "error.malformed_percent_escape")
