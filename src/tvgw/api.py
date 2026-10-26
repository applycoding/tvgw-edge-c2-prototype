"""Programmatic API."""

from __future__ import annotations

from pathlib import Path

from tvgw.corpus import load_held_out
from tvgw.encode import CodecRegistry
from tvgw.models import Detection


def load_detections(root: Path | None = None) -> list[Detection]:
    root = root or Path(__file__).resolve().parents[2]
    return load_held_out(root)


def encode_detection(det: Detection, profile: str, root: Path | None = None) -> bytes:
    root = root or Path(__file__).resolve().parents[2]
    return CodecRegistry(root).encode(det, profile, "none")
