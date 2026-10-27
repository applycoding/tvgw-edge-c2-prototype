"""Two-layer NIEM XSD + TVGW profile validation and mutation harness."""

from __future__ import annotations

import copy
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Literal
from xml.etree import ElementTree as ET

from lxml import etree

from tvgw.mapping.niem_mo import MO_NS, NC_NS, STRUCT_NS, detection_to_niem_xml
from tvgw.models import Detection

MUTATION_CLASSES = [
    "missing_name",
    "missing_time",
    "missing_location",
    "lat_non_numeric",
    "lat_out_of_range",
    "lon_out_of_range",
    "bad_datetime",
    "wrong_namespace",
    "unknown_child",
    "wrong_element_order",
    "truncated_xml",
    "empty_document",
]

LayerResult = Literal["ok", "xsd", "profile", "parse"]


@dataclass
class ValidationOutcome:
    ok: bool
    layer: LayerResult
    message: str = ""


_XSD: etree.XMLSchema | None = None


class OfflineResolver(etree.Resolver):
    def __init__(self, base: Path) -> None:
        super().__init__()
        self.base = base

    def resolve(self, url, pubid, context):  # noqa: ANN001
        if url and (url.startswith("http://") or url.startswith("https://")):
            raise OSError(f"network fetch blocked: {url}")
        if url:
            local = self.base / url
            if local.is_file():
                return self.resolve_filename(str(local), context)
        return None


def get_xsd_validator(root: Path) -> etree.XMLSchema:
    global _XSD
    if _XSD is not None:
        return _XSD
    xsd_path = root / "data/raw/niem/xsd/domains/mo.xsd"
    parser = etree.XMLParser()
    parser.resolvers.add(OfflineResolver(xsd_path.parent.parent))
    schema_doc = etree.parse(str(xsd_path), parser)
    _XSD = etree.XMLSchema(schema_doc)
    return _XSD


def validate_xsd(xml_bytes: bytes, root: Path) -> ValidationOutcome:
    try:
        doc = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError as exc:
        return ValidationOutcome(False, "parse", str(exc))
    schema = get_xsd_validator(root)
    if schema.validate(doc):
        return ValidationOutcome(True, "ok")
    return ValidationOutcome(False, "xsd", str(schema.error_log.last_error))


def validate_profile(xml_bytes: bytes) -> ValidationOutcome:
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError as exc:
        return ValidationOutcome(False, "parse", str(exc))

    if root.tag != f"{{{MO_NS}}}Observation":
        return ValidationOutcome(False, "profile", "wrong root")

    det_id = root.attrib.get(f"{{{STRUCT_NS}}}id", "")
    if not re.match(r"^[A-Za-z_][A-Za-z0-9_.-]*$", det_id):
        return ValidationOutcome(False, "profile", "invalid structures:id")

    names = root.findall(f"{{{MO_NS}}}ObservedObjectName")
    if len(names) != 1 or not (names[0].text or "").strip():
        return ValidationOutcome(False, "profile", "ObservedObjectName")
    locs = root.findall(f"{{{MO_NS}}}ObservedObjectLocation")
    if len(locs) != 1:
        return ValidationOutcome(False, "profile", "ObservedObjectLocation count")
    lat = locs[0].find(f".//{{{NC_NS}}}LatitudeDegreeValue")
    lon = locs[0].find(f".//{{{NC_NS}}}LongitudeDegreeValue")
    if lat is None or lon is None or not lat.text or not lon.text:
        return ValidationOutcome(False, "profile", "lat/lon missing")
    try:
        float(lat.text)
        float(lon.text)
    except ValueError:
        return ValidationOutcome(False, "profile", "lat/lon non-numeric")

    times = root.findall(f"{{{MO_NS}}}ObservationDateTime")
    if len(times) != 1 or not (times[0].text or "").endswith("Z"):
        return ValidationOutcome(False, "profile", "ObservationDateTime")

    for child in list(root):
        tag = child.tag
        if child.attrib.get("{http://www.w3.org/2001/XMLSchema-instance}nil") == "true":
            return ValidationOutcome(False, "profile", "xsi:nil")

    # duplicate siblings of same tag
    tags = [c.tag for c in root]
    if len(tags) != len(set(tags)):
        return ValidationOutcome(False, "profile", "duplicate siblings")

    return ValidationOutcome(True, "ok")


def count_profile_rejects(detections: list[Detection]) -> int:
    """Count TVGW profile failures. This does not run XSD validation."""
    rejects = 0
    for det in detections:
        if not validate_profile(detection_to_niem_xml(det)).ok:
            rejects += 1
    return rejects


def validate_combined(xml_bytes: bytes, root: Path) -> ValidationOutcome:
    x = validate_xsd(xml_bytes, root)
    if not x.ok:
        return x
    p = validate_profile(xml_bytes)
    return p


def apply_mutation(xml_bytes: bytes, mutation: str) -> bytes:
    if mutation == "empty_document":
        return b""
    if mutation == "truncated_xml":
        return xml_bytes[: max(10, len(xml_bytes) // 3)]
    try:
        root = etree.fromstring(xml_bytes)
    except etree.XMLSyntaxError:
        return xml_bytes

    if mutation == "missing_name":
        for el in root.xpath("//*[local-name()='ObservedObjectName']"):
            root.remove(el)
    elif mutation == "missing_time":
        for el in root.xpath("//*[local-name()='ObservationDateTime']"):
            root.remove(el)
    elif mutation == "missing_location":
        for el in root.xpath("//*[local-name()='ObservedObjectLocation']"):
            root.remove(el)
    elif mutation == "lat_non_numeric":
        el = root.xpath("//*[local-name()='LatitudeDegreeValue']")
        if el:
            el[0].text = "abc"
    elif mutation == "lat_out_of_range":
        el = root.xpath("//*[local-name()='LatitudeDegreeValue']")
        if el:
            el[0].text = "95.0"
    elif mutation == "lon_out_of_range":
        el = root.xpath("//*[local-name()='LongitudeDegreeValue']")
        if el:
            el[0].text = "-190.0"
    elif mutation == "bad_datetime":
        el = root.xpath("//*[local-name()='ObservationDateTime']")
        if el:
            el[0].text = "2026-13-45T99:99:99Z"
    elif mutation == "wrong_namespace":
        root.tag = "{http://example.com/wrong}Observation"
    elif mutation == "unknown_child":
        etree.SubElement(root, "{http://example.com/bad}Evil")
    elif mutation == "wrong_element_order":
        dt = root.xpath("//*[local-name()='ObservationDateTime']")
        if dt:
            root.insert(0, copy.deepcopy(dt[0]))
    return etree.tostring(root)
