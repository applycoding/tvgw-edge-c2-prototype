from pathlib import Path

import pytest

from tvgw.corpus import load_held_out
from tvgw.mapping.niem_mo import detection_to_niem_xml, niem_xml_to_detection
from tvgw.validate import MUTATION_CLASSES, apply_mutation, validate_combined, validate_xsd

ROOT = Path(__file__).resolve().parents[1]


def test_positive_held_out_sample():
    held = load_held_out(ROOT)
    for d in held[:50]:
        xml = detection_to_niem_xml(d)
        assert validate_combined(xml, ROOT).ok


def test_mutation_classes_rejected():
    held = load_held_out(ROOT)
    base = detection_to_niem_xml(held[0])
    for mclass in MUTATION_CLASSES:
        mut = apply_mutation(base, mclass)
        assert not validate_combined(mut, ROOT).ok


def test_missing_name_xsd_only_passes():
    base = detection_to_niem_xml(load_held_out(ROOT)[0])
    mut = apply_mutation(base, "missing_name")
    assert validate_xsd(mut, ROOT).ok
    assert not validate_combined(mut, ROOT).ok


def test_round_trip_xml_fields():
    d = load_held_out(ROOT)[0]
    xml = detection_to_niem_xml(d)
    back = niem_xml_to_detection(xml)
    assert back.detection_id == d.detection_id
    assert back.object_class == d.object_class


def test_offline_resolver_blocks_http(monkeypatch):
    from lxml import etree

    from tvgw.validate import OfflineResolver

    res = OfflineResolver(ROOT / "data/raw/niem/xsd")
    with pytest.raises(OSError):
        res.resolve("https://example.com/bad.xsd", None, None)


@pytest.mark.parametrize("mclass", MUTATION_CLASSES)
def test_each_mutation_class(mclass):
    base = detection_to_niem_xml(load_held_out(ROOT)[1])
    mut = apply_mutation(base, mclass)
    assert not validate_combined(mut, ROOT).ok
