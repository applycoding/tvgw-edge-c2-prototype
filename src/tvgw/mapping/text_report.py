"""Slash-delimited text report stand-in (non-USMTF)."""

from __future__ import annotations

import re
from datetime import datetime, timezone

from tvgw.messages import CATALOG, REPORT_TOKEN_TO_KEY, translate
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


def _escape(s: str) -> str:
    out = s
    for src, dst in ESCAPE_ORDER:
        out = out.replace(src, dst)
    return out


def _unescape_in(s: str, lang: str) -> str:
    if "%" not in s:
        return s
    pos = 0
    parts: list[str] = []
    while pos < len(s):
        if s[pos] == "%":
            if pos + 2 >= len(s) or not re.match(r"[0-9A-Fa-f]{2}", s[pos + 1 : pos + 3]):
                raise ValidationError(translate(lang, "error.malformed_percent_escape"))
            token = s[pos : pos + 3]
            parts.append(UNESCAPE.get(token, chr(int(token[1:], 16))))
            pos += 3
        else:
            parts.append(s[pos])
            pos += 1
    return "".join(parts)


def detection_to_text_report(det: Detection, lang: str = "en") -> str:
    if lang not in CATALOG:
        raise ValidationError(translate("en", "error.unsupported_language", lang=lang))
    labels = CATALOG[lang]
    dtg = det.timestamp_utc.strftime("%Y%m%dT%H%M%SZ")
    pri = f"P{int(det.priority)}"
    lines = [
        f"{labels['report.msgid']}/{labels['report.kind']}/001/{pri}/{lang.upper()}//",
        (
            f"{labels['report.dtg']}/{dtg}/{labels['report.src']}/{_escape(det.source_sensor)}/"
            f"{labels['report.dom']}/{det.domain}/{labels['report.svc']}/{det.functional_service}//"
        ),
        (
            f"{labels['report.obj']}/{det.object_class.upper()}/{labels['report.conf']}/"
            f"{det.confidence_score:.4f}/{labels['report.id']}/{det.detection_id}//"
        ),
    ]
    lat = f"{abs(det.latitude_deg):.5f}{'N' if det.latitude_deg >= 0 else 'S'}"
    lon = f"{abs(det.longitude_deg):.5f}{'E' if det.longitude_deg >= 0 else 'W'}"
    alt_part = (
        f"/{labels['report.alt']}/{det.altitude_m:.1f}M" if det.altitude_m is not None else ""
    )
    lines.append(f"{labels['report.loc']}/{lat}/{lon}{alt_part}//")
    if det.attributes:
        rmk = ";".join(
            f"{_escape(str(k))}={_escape(str(v))}" for k, v in sorted(det.attributes.items())
        )
        lines.append(f"{labels['report.rmk']}/{rmk}//")
    lines.append(f"{labels['report.end']}//")
    return "\n".join(lines) + "\n"


def _lang_from_msgid(msgid_parts: list[str]) -> str:
    # parts after the set name: kind / 001 / P# / LANG / ...
    if len(msgid_parts) > 3 and msgid_parts[3].lower() in CATALOG:
        return msgid_parts[3].lower()
    return "en"


def text_report_to_detection(text: str) -> Detection:
    lines = [ln.strip() for ln in text.strip().splitlines() if ln.strip()]
    fields: dict[str, list[str]] = {}
    for line in lines:
        parts = line.split("/")
        canon = REPORT_TOKEN_TO_KEY.get(parts[0])
        if canon == "report.end" or canon is None:
            continue
        fields[canon] = parts[1:]

    msgid = fields.get("report.msgid", [])
    lang = _lang_from_msgid(msgid)
    pri_token = msgid[2] if len(msgid) > 2 else "P2"
    priority = Priority(int(pri_token[1]) if pri_token.startswith("P") else 2)

    dtg_parts = fields.get("report.dtg", [])
    dtg = dtg_parts[0] if dtg_parts else "19700101T000000Z"
    ts = datetime.strptime(dtg, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
    src = _unescape_in(dtg_parts[2], lang) if len(dtg_parts) > 2 else "UNKNOWN"
    domain = OperationalDomain(dtg_parts[4]) if len(dtg_parts) > 4 else OperationalDomain.AIR
    svc = FunctionalService(dtg_parts[6]) if len(dtg_parts) > 6 else FunctionalService.INTEL

    obj_parts = fields.get("report.obj", [])
    obj_class = _unescape_in(obj_parts[0], lang).lower() if obj_parts else "other"
    conf = float(obj_parts[2]) if len(obj_parts) > 2 else 0.5
    det_id = obj_parts[4] if len(obj_parts) > 4 else "UNKNOWN_1"

    loc = fields.get("report.loc", [])
    lat_token = loc[0] if loc else "0N"
    lon_token = loc[1] if len(loc) > 1 else "0E"
    lat = float(lat_token[:-1]) * (1 if lat_token[-1] == "N" else -1)
    lon = float(lon_token[:-1]) * (1 if lon_token[-1] == "E" else -1)
    alt = None
    alt_label = CATALOG[lang]["report.alt"]
    if len(loc) > 3 and loc[2] == alt_label:
        alt = float(loc[3].rstrip("M"))

    attrs: dict[str, str] = {}
    rmk_parts = fields.get("report.rmk", [])
    if rmk_parts and rmk_parts[0]:
        # Validate escapes on the raw field, then split on literal ';' so %3B stays in the value.
        _unescape_in(rmk_parts[0], lang)
        for pair in rmk_parts[0].split(";"):
            if "=" not in pair:
                continue
            key, value = pair.split("=", 1)
            attrs[_unescape_in(key, lang)] = _unescape_in(value, lang)

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
