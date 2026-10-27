#!/usr/bin/env python3
"""Rule-based cross-source association benchmark on the committed FIRMS snapshot.

Exact command from the repository root:

    .venv/bin/python scripts/bench_association.py

Writes results/m4_association.csv and results/m4_association.json.
The M3 delivery grid does not call this step. Bytes are CBOR payload sizes
before transmission. Merged detections are records removed from the transmit
set; their positions and confidences are not kept except for the winning record
and the contributor id list.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tvgw.associate import associate_for_transmission, window_pair_counts, windows_from_config
from tvgw.config_loader import load_config
from tvgw.encode import CodecRegistry
from tvgw.sources.firms import load_firms_detections

COMMAND = ".venv/bin/python scripts/bench_association.py"
DATASET = "data/sample/firms_canada_24h_snapshot.csv"
CSV_NAME = "m4_association.csv"
JSON_NAME = "m4_association.json"
CSV_FIELDS = [
    "dataset",
    "sensor_id_from",
    "max_distance_m",
    "max_time_s",
    "allow_cross_class",
    "input_messages",
    "output_messages",
    "messages_saved",
    "bytes_in_cbor",
    "bytes_out_cbor",
    "bytes_saved",
    "merged_detections",
    "multi_source_clusters",
    "same_sensor_pairs_within_window",
    "different_sensor_pairs_within_window",
    "different_class_pairs_within_window",
]


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def _cbor_bytes(codec: CodecRegistry, detections: list) -> int:
    return sum(len(codec.encode(det, "cbor", "none")) for det in detections)


def build_report(root: Path) -> dict:
    cfg = load_config(root)
    windows = windows_from_config(cfg)
    dataset = root / DATASET
    detections = load_firms_detections(dataset, sensor_id_from="satellite")
    outcome = associate_for_transmission(detections, windows)
    pairs = window_pair_counts(detections, windows)
    codec = CodecRegistry(root)
    bytes_in = _cbor_bytes(codec, detections)
    bytes_out = _cbor_bytes(codec, list(outcome.records))
    row = {
        "dataset": DATASET,
        "sensor_id_from": "satellite",
        "max_distance_m": windows.max_distance_m,
        "max_time_s": windows.max_time_s,
        "allow_cross_class": windows.allow_cross_class,
        "input_messages": outcome.input_count,
        "output_messages": outcome.output_count,
        "messages_saved": outcome.messages_saved,
        "bytes_in_cbor": bytes_in,
        "bytes_out_cbor": bytes_out,
        "bytes_saved": bytes_in - bytes_out,
        "merged_detections": outcome.merged_detection_count,
        "multi_source_clusters": outcome.multi_source_cluster_count,
        "same_sensor_pairs_within_window": pairs["same_sensor_same_class"],
        "different_sensor_pairs_within_window": pairs["different_sensor_same_class"],
        "different_class_pairs_within_window": pairs["different_class"],
    }
    return {
        "command": COMMAND,
        "dataset_sha256": _sha256(dataset),
        "byte_profile": "cbor",
        "note": (
            "Rule-based cross-source association on the committed NASA FIRMS Canada 24h snapshot. "
            "Sensor identity for this table is the CSV satellite column (FIRMS-<satellite>), which "
            "is a single value in this file, so different sensors do not occur. "
            "same_sensor_pairs_within_window counts overlaps the rule leaves unmerged. "
            "This is not a score of whether a hotspot was correct, and it is not part of the M3 grid."
        ),
        "row": row,
    }


def write_report(root: Path, results_dir: Path) -> dict:
    report = build_report(root)
    results_dir.mkdir(parents=True, exist_ok=True)
    csv_path = results_dir / CSV_NAME
    with csv_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerow(report["row"])
    report["csv_sha256"] = _sha256(csv_path)
    json_path = results_dir / JSON_NAME
    json_path.write_text(json.dumps(report, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return report


def main() -> None:
    parser = argparse.ArgumentParser(description="Cross-source association benchmark")
    parser.add_argument("--results-dir", default=str(ROOT / "results"))
    args = parser.parse_args()
    report = write_report(ROOT, Path(args.results_dir))
    row = report["row"]
    print(
        "messages_saved={messages_saved} bytes_saved={bytes_saved} "
        "merged_detections={merged_detections} same_sensor_pairs_within_window={pairs}".format(
            messages_saved=row["messages_saved"],
            bytes_saved=row["bytes_saved"],
            merged_detections=row["merged_detections"],
            pairs=row["same_sensor_pairs_within_window"],
        )
    )


if __name__ == "__main__":
    main()
