#!/usr/bin/env python3
"""Download HIT-UAV annotations, FIRMS snapshot, and build corpus splits."""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
HITUAV_COMMIT = "669259659b21a2737ca9f5e4bc81892acbe6ecd8"
HITUAV_BASE = (
    f"https://raw.githubusercontent.com/suojiashun/"
    f"HIT-UAV-Infrared-Thermal-Dataset/{HITUAV_COMMIT}"
)
FIRMS_URL = (
    "https://firms.modaps.eosdis.nasa.gov/data/active_fire/"
    "noaa-20-viirs-c2/csv/J1_VIIRS_C2_Canada_24h.csv"
)

HITUAV_FILES = {
    "train.json": "4e6e93966ec366ce63aa120f038c52e792b02811ff2ab2d43ef56e6561aceff1",
    "val.json": "9b34b423b6b1602b87e88b7f9864fa4273b73c280846ba6cb1b90c2e6761873e",
    "test.json": "f29545df4b27bb09fa705b0d2865f69f5ef7cdf81930b84dcc9dd0df63c71d19",
}
SAMPLE_JPG = "normal_json/test/0_100_30_0_03307.jpg"
SAMPLE_JPG_SHA256 = "92e92314e9b61d3ae59179ecf63200b623db63e317e6fb351cdb83adf53415ad"
FIRMS_SNAPSHOT_SHA256 = "eceac7905c3aedd66578c8c2b1a01cde7f5fafc8ac387aa0359c2367a919bf1b"

HITUAV_REMOTE = {
    "train.json": "normal_json/annotations/train.json",
    "val.json": "normal_json/annotations/val.json",
    "test.json": "normal_json/annotations/test.json",
}


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def download_url(url: str, dest: Path, expected_sha256: str) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.is_file():
        digest = sha256_file(dest)
        if digest != expected_sha256:
            raise SystemExit(f"SHA-256 mismatch for {dest.name}: got {digest}, expected {expected_sha256}")
        return
    print(f"Downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp:
        dest.write_bytes(resp.read())
    digest = sha256_file(dest)
    if digest != expected_sha256:
        dest.unlink(missing_ok=True)
        raise SystemExit(f"SHA-256 mismatch for {dest.name}: got {digest}, expected {expected_sha256}")


def build_corpus_manifest() -> dict:
    sys.path.insert(0, str(ROOT / "src"))
    from tvgw.corpus import write_corpus_artifacts

    return write_corpus_artifacts(ROOT)


def main() -> None:
    raw = ROOT / "data" / "raw" / "hituav"
    for local_name, expected in HITUAV_FILES.items():
        rel = HITUAV_REMOTE[local_name]
        download_url(f"{HITUAV_BASE}/{rel}", raw / local_name, expected)

    sample_dir = ROOT / "data" / "sample"
    download_url(f"{HITUAV_BASE}/{SAMPLE_JPG}", sample_dir / "sample_thermal_0_100_30_0_03307.jpg", SAMPLE_JPG_SHA256)

    firms_path = sample_dir / "firms_canada_24h_snapshot.csv"
    if not firms_path.is_file():
        download_url(FIRMS_URL, firms_path, FIRMS_SNAPSHOT_SHA256)
    else:
        digest = sha256_file(firms_path)
        if digest != FIRMS_SNAPSHOT_SHA256:
            raise SystemExit(f"FIRMS snapshot SHA-256 mismatch: got {digest}, expected {FIRMS_SNAPSHOT_SHA256}")

    text = firms_path.read_text(encoding="utf-8", errors="replace")
    lines = [ln for ln in text.strip().splitlines() if ln.strip()]
    if len(lines) < 2:
        raise SystemExit("FIRMS CSV appears empty or invalid")
    data_rows = len(lines) - 1

    manifest = build_corpus_manifest()
    manifest["firms_rows"] = data_rows
    manifest["firms_sha256"] = sha256_file(firms_path)
    manifest["firms_retrieved_utc"] = datetime.now(timezone.utc).isoformat()
    manifest["hituav_git_commit"] = HITUAV_COMMIT

    out = ROOT / "data" / "raw" / "download_manifest.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(manifest, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(f"Wrote {out}")


if __name__ == "__main__":
    main()
