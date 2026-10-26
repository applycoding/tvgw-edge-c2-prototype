"""Slash-delimited text report stand-in (non-USMTF)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from tvgw.models import Detection, FunctionalService, OperationalDomain, Priority, ValidationError

ESCAPE_ORDER = [
    ("%", "%25"),
    ("/", "%2F"),
    (";", "%3B"),
    ("|", "%7C"),
    ("\r", "%0D"),
    ("\n", "%0A"),
]

UNESCAPE = {v: k for k, v in ESCAPE_ORDER}
UNESCAPE["%25"] = "%"
HEX_ESCAPE_RE = re.compile(r"%[0-9A-Fa-f]{2}")


def _escape(s: str) -> str:
    out = s
    for src, dst in ESCAPE_ORDER:
        out = out.replace(src, dst)
    return out


def _unescape(s: str) -> str:
    if "%" in s:
        pos = 0
        parts: list[str] = []
        while pos < len(s):
            if s[pos] == "%":
                if pos + 2 >= len(s) or not re.match(r"[0-9A-Fa-f]{2}", s[pos + 1 : pos + 3]):
                    raise ValidationError("malformed percent escape")
                token = s[pos : pos + 3]
                parts.append(UNESCAPE.get(token, chr(int(token[1:], 16))))
                pos += 3
            else:
                parts.append(s[pos])
                pos += 1
        return "".join(parts)
    return s


def detection_to_text_report(det: Detection, lang: str = "en") -> str:
    dtg = det.timestamp_utc.strftime("%Y%m%dT%H%M%SZ")
    pri = f"P{int(det.priority)}"
    lines = [
        f"MSGID/TVGW-SPOT-STANDIN/001/{pri}/{lang.upper()}//",
        (
            f"DTG/{dtg}/SRC/{_escape(det.source_sensor)}/"
            f"DOM/{det.domain}/SVC/{det.functional_service}//"
        ),
        (
            f"OBJ/{det.object_class.upper()}/CONF/{det.confidence_score:.4f}/"
            f"ID/{det.detection_id}//"
        ),
    ]
    lat = f"{abs(det.latitude_deg):.5f}{'N' if det.latitude_deg >= 0 else 'S'}"
    lon = f"{abs(det.longitude_deg):.5f}{'E' if det.longitude_deg >= 0 else 'W'}"
    alt_part = f"/ALT/{det.altitude_m:.1f}M" if det.altitude_m is not None else ""
    lines.append(f"LOC/{lat}/{lon}{alt_part}//")
    if det.attributes:
        rmk = ";".join(f"{_escape(str(k))}={_escape(str(v))}" for k, v in sorted(det.attributes.items()))
        lines.append(f"RMK/{rmk}//")
    lines.append("ENDAT//")
    return "\n".join(lines) + "\n"


def text_report_to_detection(text: str) -> Detection:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    fields: dict[str, list[str]] = {}
    for line in lines:
        if line == "ENDAT//":
            continue
        parts = line.split("/")
        key = parts[0]
        fields[key] = parts[1:]

    msgid = fields.get("MSGID", [])
    pri_token = msgid[3] if len(msgid) > 3 else "P2"
    priority = Priority(int(pri_token[1]) if pri_token.startswith("P") else 2)

    dtg_parts = fields.get("DTG", [])
    dtg = dtg_parts[0] if dtg_parts else "19700101T000000Z"
    ts = datetime.strptime(dtg, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    src = _unescape(dtg_parts[2]) if len(dtg_parts) > 2 else "UNKNOWN"
    domain = OperationalDomain(dtg_parts[4]) if len(dtg_parts) > 4 else OperationalDomain.AIR
    svc = FunctionalService(dtg_parts[6]) if len(dtg_parts) > 6 else FunctionalService.INTEL

    obj_parts = fields.get("OBJ", [])
    obj_class = _unescape(obj_parts[0]).lower() if obj_parts else "other"
    conf = float(obj_parts[2]) if len(obj_parts) > 2 else 0.5
    det_id = obj_parts[4] if len(obj_parts) > 4 else "UNKNOWN_1"

    loc = fields.get("LOC", [])
    lat_token = loc[0] if loc else "0N"
    lon_token = loc[1] if len(loc) > 1 else "0E"
    lat = float(lat_token[:-1]) * (1 if lat_token[-1] == "N" else -1)
    lon = float(lon_token[:-1]) * (1 if lon_token[-1] == "E" else -1)
    alt = None
    if len(loc) > 3 and loc[2] == "ALT":
        alt = float(loc[3].rstrip("M"))

    attrs: dict[str, str] = {}
    if "RMK" in fields and fields["RMK"]:
        for pair in _unescape(fields["RMK"][0]).split(";"):
            if "=" in pair:
                k, v = pair.split("=", 1)
                attrs[k] = v

    return Detection(
        detection_id=det_id,
        timestamp_utc=ts,
        source_sensor=src,
        domain=domain,
        functional_service=svc,
        object_class=obj_class,
        confidence_score=conf,
        latitude_deg=lat,
        longitude_deg=lon,
        priority=priority,
        altitude_m=alt,
        attributes=attrs,
    )
