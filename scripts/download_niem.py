#!/usr/bin/env python3
"""Download and extract OASIS NIEMOpen 6.0 model zip with SHA-256 pinning."""

from __future__ import annotations

import hashlib
import json
import sys
import urllib.request
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
NIEM_URL = (
    "https://docs.oasis-open.org/niemopen/niem-model/v6.0/os/niem-model-v6.0-os.zip"
)
ZIP_PATH = ROOT / "data" / "raw" / "niem-model-v6.0-os.zip"
XSD_ROOT = ROOT / "data" / "raw" / "niem" / "xsd"
MANIFEST = ROOT / "data" / "raw" / "niem_manifest.json"
PINNED_SHA256 = "2b899067b5312333935329e6e7665e1eb295f392a51d4a56bc9800dbcc42fcfa"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def load_manifest() -> dict:
    if MANIFEST.is_file():
        return json.loads(MANIFEST.read_text(encoding="utf-8"))
    return {}


def save_manifest(data: dict) -> None:
    MANIFEST.parent.mkdir(parents=True, exist_ok=True)
    MANIFEST.write_text(json.dumps(data, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def download() -> None:
    ZIP_PATH.parent.mkdir(parents=True, exist_ok=True)
    expected = PINNED_SHA256

    if ZIP_PATH.is_file():
        digest = sha256_file(ZIP_PATH)
        if digest != expected:
            raise SystemExit(f"NIEM zip SHA-256 mismatch: got {digest}, expected {expected}")
        print(f"NIEM zip already present with matching SHA-256: {expected}")
        extract()
        return

    print(f"Downloading NIEM 6.0 from {NIEM_URL}")
    with urllib.request.urlopen(NIEM_URL, timeout=120) as resp:
        data = resp.read()
    ZIP_PATH.write_bytes(data)
    digest = sha256_file(ZIP_PATH)
    if digest != expected:
        ZIP_PATH.unlink(missing_ok=True)
        raise SystemExit(f"NIEM zip SHA-256 mismatch: got {digest}, expected {expected}")
    manifest = load_manifest()
    manifest["zip_sha256"] = digest
    manifest["url"] = NIEM_URL
    save_manifest(manifest)
    print(f"NIEM zip SHA-256: {digest}")
    extract()


def extract() -> None:
    mo_xsd = XSD_ROOT / "domains" / "mo.xsd"
    if mo_xsd.is_file():
        return
    XSD_ROOT.parent.mkdir(parents=True, exist_ok=True)
    extract_root = ROOT / "data" / "raw" / "niem"
    with zipfile.ZipFile(ZIP_PATH, "r") as zf:
        zf.extractall(extract_root)
    if not mo_xsd.is_file():
        raise SystemExit("mo.xsd not found after extraction")


if __name__ == "__main__":
    try:
        download()
    except Exception as exc:  # noqa: BLE001
        print(f"download_niem failed: {exc}", file=sys.stderr)
        raise
