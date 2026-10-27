"""Build canonical corpus and train/held-out splits."""

from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

from tvgw.models import Detection, FunctionalService, OperationalDomain, Priority
from tvgw.sources.firms import load_firms_detections
from tvgw.sources.hituav import load_all_hituav

# Held-in split used to train the zstd dictionary. The IDs are NASA FIRMS
# record IDs (they sort before HIT-UAV IDs); the historical filename was misleading.
TRAIN_IDS_FILENAME = "firms_train_ids_500.json"


def build_full_corpus(root: Path) -> list[Detection]:
    hit = load_all_hituav(root / "data" / "raw" / "hituav", exclude_dontcare=True)
    firms = load_firms_detections(root / "data" / "sample" / "firms_canada_24h_snapshot.csv")
    all_d: list[Detection] = hit + firms
    seen: set[str] = set()
    unique: list[Detection] = []
    for d in all_d:
        if d.detection_id in seen:
            continue
        seen.add(d.detection_id)
        unique.append(d)
    unique.sort(key=lambda d: d.detection_id)
    return unique


def write_corpus_artifacts(root: Path) -> dict:
    corpus = build_full_corpus(root)
    if len(corpus) < 5500:
        raise RuntimeError(f"corpus too small: {len(corpus)}")
    train = corpus[:500]
    held_out = corpus[500:5500]
    train_ids = [d.detection_id for d in train]
    train_path = train_ids_path(root)
    train_path.write_text(json.dumps(train_ids, indent=2) + "\n", encoding="utf-8")

    held_path = root / "data" / "corpus" / "held_out_5000.jsonl"
    held_path.parent.mkdir(parents=True, exist_ok=True)
    with held_path.open("w", encoding="utf-8") as f:
        for d in held_out:
            f.write(json.dumps(_det_to_dict(d)) + "\n")

    manifest = {
        "corpus_total": len(corpus),
        "train_count": len(train),
        "held_out_count": len(held_out),
        "hituav_annotation_count": len([d for d in corpus if d.detection_id.startswith("HITUAV")]),
        "hituav_image_count": 2898,
    }
    raw = root / "data" / "raw" / "hituav"
    for name, key in [("train.json", "hituav_train_sha256"), ("val.json", "hituav_val_sha256"), ("test.json", "hituav_test_sha256")]:
        p = raw / name
        if p.is_file():
            manifest[key] = _sha(p)
    sample_jpg = root / "data" / "sample" / "sample_thermal_0_100_30_0_03307.jpg"
    if sample_jpg.is_file():
        manifest["sample_jpeg_sha256"] = _sha(sample_jpg)
    manifest["train_ids_sha256"] = _sha(train_path)
    manifest["held_out_corpus_sha256"] = _sha(held_path)
    niem_manifest = root / "data" / "raw" / "niem_manifest.json"
    if niem_manifest.is_file():
        nm = json.loads(niem_manifest.read_text())
        manifest["niem_zip_sha256"] = nm.get("zip_sha256")
        manifest["niem_url"] = nm.get("url")
    return manifest


def load_held_out(root: Path) -> list[Detection]:
    path = root / "data" / "corpus" / "held_out_5000.jsonl"
    out: list[Detection] = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            out.append(_dict_to_det(json.loads(line)))
    return out


def train_ids_path(root: Path) -> Path:
    return root / "data" / "sample" / TRAIN_IDS_FILENAME


def load_train_ids(root: Path) -> set[str]:
    return set(json.loads(train_ids_path(root).read_text(encoding="utf-8")))


def _sha(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _det_to_dict(d: Detection) -> dict:
    return {
        "detection_id": d.detection_id,
        "timestamp_utc": d.timestamp_utc.isoformat().replace("+00:00", "Z"),
        "source_sensor": d.source_sensor,
        "domain": str(d.domain),
        "functional_service": str(d.functional_service),
        "object_class": d.object_class,
        "confidence_score": d.confidence_score,
        "latitude_deg": d.latitude_deg,
        "longitude_deg": d.longitude_deg,
        "priority": int(d.priority),
        "altitude_m": d.altitude_m,
        "attributes": d.attributes,
    }


def _dict_to_det(data: dict) -> Detection:
    ts = datetime.fromisoformat(data["timestamp_utc"].replace("Z", "+00:00"))
    return Detection(
        detection_id=data["detection_id"],
        timestamp_utc=ts.astimezone(timezone.utc),
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
