"""Codec registry and compression wrappers."""

from __future__ import annotations

import gzip
import json
from dataclasses import dataclass
from enum import IntEnum
from pathlib import Path
from typing import Callable

import cbor2
import zstandard as zstd

from tvgw.mapping.niem_mo import detection_to_niem_xml, niem_xml_to_detection
from tvgw.mapping.text_report import detection_to_text_report, text_report_to_detection
from tvgw.models import Detection


class CodecId(IntEnum):
    XML = 1
    TEXT = 2
    JSON = 3
    CBOR = 4


class CompressionFlag(IntEnum):
    NONE = 0x00
    GZIP = 0x10
    ZSTD = 0x20
    ZSTD_DICT = 0x30


@dataclass
class CodecRegistry:
    root: Path
    zstd_dict: zstd.ZstdCompressionDict | None = None

    def __post_init__(self) -> None:
        dict_path = self.root / "data/sample/niem_zstd.dict"
        if dict_path.is_file():
            self.zstd_dict = zstd.ZstdCompressionDict(dict_path.read_bytes())

    def encode(self, det: Detection, profile: str, compression: str = "none") -> bytes:
        raw = self._encode_raw(det, profile)
        return self._compress(raw, profile, compression)

    def decode(self, payload: bytes, profile: str, compression: str = "none") -> Detection:
        raw = self._decompress(payload, profile, compression)
        return self._decode_raw(raw, profile)

    def _encode_raw(self, det: Detection, profile: str) -> bytes:
        if profile in ("niem_mo_observation", "xml_raw", "xml"):
            return detection_to_niem_xml(det)
        if profile in ("spotrep_style_text", "text_raw", "text"):
            return detection_to_text_report(det).encode("utf-8")
        if profile in ("json", "json_raw"):
            return json.dumps(_det_json(det), separators=(",", ":"), sort_keys=True).encode()
        if profile in ("cbor", "cbor_raw"):
            return cbor2.dumps(_det_json(det))
        raise ValueError(f"unknown profile {profile}")

    def _decode_raw(self, raw: bytes, profile: str) -> Detection:
        if profile.startswith("xml") or profile == "niem_mo_observation":
            return niem_xml_to_detection(raw)
        if profile.startswith("text") or profile == "spotrep_style_text":
            return text_report_to_detection(raw.decode("utf-8"))
        if profile.startswith("json"):
            return _json_to_det(json.loads(raw.decode()))
        if profile.startswith("cbor"):
            return _json_to_det(cbor2.loads(raw))
        raise ValueError(profile)

    def _compress(self, raw: bytes, profile: str, compression: str) -> bytes:
        if compression in ("none", "raw"):
            return raw
        if compression == "gzip":
            return gzip.compress(raw)
        if compression == "zstd":
            return zstd.ZstdCompressor().compress(raw)
        if compression == "zstd_dict":
            if self.zstd_dict is None:
                raise RuntimeError("zstd dictionary missing")
            return zstd.ZstdCompressor(dict_data=self.zstd_dict).compress(raw)
        return raw

    def _decompress(self, payload: bytes, profile: str, compression: str) -> bytes:
        if compression in ("none", "raw"):
            return payload
        if compression == "gzip":
            return gzip.decompress(payload)
        if compression == "zstd":
            return zstd.ZstdDecompressor().decompress(payload)
        if compression == "zstd_dict":
            if self.zstd_dict is None:
                raise RuntimeError("zstd dictionary missing")
            return zstd.ZstdDecompressor(dict_data=self.zstd_dict).decompress(payload)
        return payload


def train_zstd_dictionary(root: Path, train_xml: list[bytes], dict_size: int = 16384) -> Path:
    samples = [x for x in train_xml if x]
    dict_data = zstd.train_dictionary(dict_size, samples)
    out = root / "data/sample/niem_zstd.dict"
    out.write_bytes(dict_data.as_bytes())
    return out


def _det_json(det: Detection) -> dict:
    return {
        "detection_id": det.detection_id,
        "timestamp_utc": det.timestamp_utc.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "source_sensor": det.source_sensor,
        "domain": str(det.domain),
        "functional_service": str(det.functional_service),
        "object_class": det.object_class,
        "confidence_score": det.confidence_score,
        "latitude_deg": det.latitude_deg,
        "longitude_deg": det.longitude_deg,
        "priority": int(det.priority),
        "altitude_m": det.altitude_m,
        "attributes": det.attributes,
    }


def _json_to_det(data: dict) -> Detection:
    from datetime import datetime, timezone

    from tvgw.models import FunctionalService, OperationalDomain, Priority

    ts = datetime.strptime(data["timestamp_utc"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=timezone.utc)
    return Detection(
        detection_id=data["detection_id"],
        timestamp_utc=ts,
        source_sensor=data["source_sensor"],
        domain=OperationalDomain(data["domain"]),
        functional_service=FunctionalService(data["functional_service"]),
        object_class=data["object_class"],
        confidence_score=data["confidence_score"],
        latitude_deg=data["latitude_deg"],
        longitude_deg=data["longitude_deg"],
        priority=Priority(data["priority"]),
        altitude_m=data.get("altitude_m"),
        attributes=data.get("attributes", {}),
    )
