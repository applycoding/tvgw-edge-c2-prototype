import json
from pathlib import Path

from scripts.bench_association import COMMAND, build_report

ROOT = Path(__file__).resolve().parents[1]


def test_committed_association_benchmark_matches_rerun():
    committed = json.loads((ROOT / "results" / "m4_association.json").read_text(encoding="utf-8"))
    fresh = build_report(ROOT)
    assert committed["command"] == COMMAND == ".venv/bin/python scripts/bench_association.py"
    assert committed["row"] == fresh["row"]
    assert committed["dataset_sha256"] == fresh["dataset_sha256"]
    assert committed["row"]["messages_saved"] == committed["row"]["merged_detections"]
    assert committed["row"]["bytes_saved"] == committed["row"]["bytes_in_cbor"] - committed["row"]["bytes_out_cbor"]
    summary = (ROOT / "results" / "SUMMARY.md").read_text(encoding="utf-8")
    assert ".venv/bin/python scripts/bench_association.py" in summary
    assert str(committed["row"]["same_sensor_pairs_within_window"]) in summary
