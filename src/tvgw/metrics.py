"""Prometheus and HEC-shaped exporters."""

from __future__ import annotations

import csv
import json
from pathlib import Path


def export_prometheus(root: Path) -> None:
    cells = root / "results/m3_delivery_cells.csv"
    lines = [
        "# HELP tvgw_p0_within_deadline P0 within-deadline delivery ratio (cell means)",
        "# TYPE tvgw_p0_within_deadline summary",
    ]
    count = 0
    total = 0.0
    if cells.is_file():
        with cells.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                try:
                    val = float(row.get("p0_within_deadline_mean", "nan"))
                except ValueError:
                    continue
                if val != val:
                    continue
                total += val
                count += 1
    mean = total / count if count else 0.0
    lines.append(f'tvgw_p0_within_deadline_sum{{mode="lab"}} {total}')
    lines.append(f'tvgw_p0_within_deadline_count{{mode="lab"}} {count}')
    lines.append(f'tvgw_p0_within_deadline{{mode="lab",quantile="0.5"}} {mean}')
    (root / "results/metrics.prom").write_text("\n".join(lines) + "\n", encoding="utf-8")


def export_splunk_hec(root: Path) -> None:
    event = {"event": {"source": "tvgw", "metric": "bench_complete"}, "time": 1}
    (root / "results/splunk_hec_events.jsonl").write_text(json.dumps(event) + "\n", encoding="utf-8")
