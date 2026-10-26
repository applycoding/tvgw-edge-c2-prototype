"""Detection <-> NIEM 6.0 mo:Observation XML."""

from __future__ import annotations

from datetime import datetime
from xml.etree import ElementTree as ET

from tvgw.models import Detection

MO_NS = "https://docs.oasis-open.org/niemopen/ns/model/domains/militaryOperations/6.0/"
NC_NS = "https://docs.oasis-open.org/niemopen/ns/model/niem-core/6.0/"
STRUCT_NS = "https://docs.oasis-open.org/niemopen/ns/model/structures/6.0/"

ET.register_namespace("mo", MO_NS)
ET.register_namespace("nc", NC_NS)
ET.register_namespace("structures", STRUCT_NS)


def detection_to_niem_xml(det: Detection) -> bytes:
    root = ET.Element(
        f"{{{MO_NS}}}Observation",
        {
            f"{{{STRUCT_NS}}}id": det.detection_id,
        },
    )
    name = ET.SubElement(root, f"{{{MO_NS}}}ObservedObjectName")
    if det.source_sensor == "HIT-UAV-IR":
        name.text = f"[SYNTH-GPS] {det.object_class}"
    else:
        name.text = det.object_class

    loc = ET.SubElement(root, f"{{{MO_NS}}}ObservedObjectLocation")
    coord = ET.SubElement(loc, f"{{{MO_NS}}}ObservedObject2DGeospatialCoordinate")
    lat_el = ET.SubElement(coord, f"{{{NC_NS}}}GeographicCoordinateLatitude")
    lat_val = ET.SubElement(lat_el, f"{{{NC_NS}}}LatitudeDegreeValue")
    lat_val.text = f"{det.latitude_deg:.5f}"
    lon_el = ET.SubElement(coord, f"{{{NC_NS}}}GeographicCoordinateLongitude")
    lon_val = ET.SubElement(lon_el, f"{{{NC_NS}}}LongitudeDegreeValue")
    lon_val.text = f"{det.longitude_deg:.5f}"

    dt_el = ET.SubElement(root, f"{{{MO_NS}}}ObservationDateTime")
    dt_el.text = det.timestamp_utc.strftime("%Y-%m-%dT%H:%M:%SZ")

    return ET.tostring(root, encoding="utf-8", xml_declaration=False)


def niem_xml_to_detection(xml_bytes: bytes) -> Detection:
    from tvgw.models import FunctionalService, OperationalDomain, Priority

    root = ET.fromstring(xml_bytes)
    det_id = root.attrib.get(f"{{{STRUCT_NS}}}id") or root.attrib.get("structures:id", "")
    name_el = root.find(f"{{{MO_NS}}}ObservedObjectName")
    obj_class = (name_el.text or "").strip() if name_el is not None else ""
    if obj_class.startswith("[SYNTH-GPS] "):
        obj_class = obj_class[len("[SYNTH-GPS] ") :]
    lat = lon = None
    loc = root.find(f"{{{MO_NS}}}ObservedObjectLocation")
    if loc is not None:
        lat_el = loc.find(f".//{{{NC_NS}}}LatitudeDegreeValue")
        lon_el = loc.find(f".//{{{NC_NS}}}LongitudeDegreeValue")
        if lat_el is not None and lat_el.text:
            lat = float(lat_el.text)
        if lon_el is not None and lon_el.text:
            lon = float(lon_el.text)
    dt_el = root.find(f"{{{MO_NS}}}ObservationDateTime")
    from datetime import timezone

    ts_text = dt_el.text if dt_el is not None else "1970-01-01T00:00:00Z"
    ts = datetime.strptime(ts_text, "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return Detection(
        detection_id=det_id,
        timestamp_utc=ts,
        source_sensor="NIEM-IMPORT",
        domain=OperationalDomain.AIR,
        functional_service=FunctionalService.INTEL,
        object_class=obj_class,
        confidence_score=0.5,
        latitude_deg=lat if lat is not None else 0.0,
        longitude_deg=lon if lon is not None else 0.0,
        priority=Priority.P2_ROUTINE,
    )
