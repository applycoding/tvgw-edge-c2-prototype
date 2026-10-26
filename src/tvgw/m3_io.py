"""Read/write M3 delivery sweep artifacts (CSV, gzip, per-cell aggregate)."""

from __future__ import annotations

import csv
import gzip
import io
import statistics
from collections import defaultdict
from pathlib import Path
from typing import Any, Iterator

import numpy as np

CELLS_NAME = "m3_delivery_cells.csv"
GZIP_NAME = "m3_delivery_sweep.csv.gz"
RAW_NAME = "m3_delivery_sweep.csv"


def m3_runs_path(results_dir: Path) -> Path:
    raw = results_dir / RAW_NAME
    if raw.is_file():
        return raw
    gz = results_dir / GZIP_NAME
    if gz.is_file():
        return gz
    return raw


def iter_m3_run_rows(results_dir: Path) -> Iterator[dict[str, str]]:
    path = m3_runs_path(results_dir)
    if not path.is_file():
        return iter(())
    if path.suffix == ".gz":
        with gzip.open(path, "rt", encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)
    else:
        with path.open(encoding="utf-8", newline="") as f:
            yield from csv.DictReader(f)


def aggregate_m3_cells(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Aggregate per-seed rows into per-cell summaries for plots and SUMMARY."""
    by_cell: dict[tuple, list[dict]] = defaultdict(list)
    ci_rows: dict[tuple, dict] = {}
    for row in rows:
        if row.get("scheduling") == "paired_ci":
            key = (row["rate_bps"], row["loss_rate"], row["profile"])
            ci_rows[key] = row
            continue
        if row.get("seed") == "-1":
            continue
        key = (row["rate_bps"], row["loss_rate"], row["profile"], row["scheduling"])
        by_cell[key].append(row)

    out: list[dict[str, Any]] = []
    for key, samples in sorted(by_cell.items(), key=lambda kv: (float(kv[0][0]), float(kv[0][1]), kv[0][2], kv[0][3])):
        rate, loss, profile, sched = key
        p0_vals = [float(r["p0_within_deadline_ratio"]) for r in samples]
        gp_vals = [float(r["goodput_bps"]) for r in samples if r.get("goodput_bps")]
        cens = [int(float(r.get("censored_count", 0))) for r in samples]
        ci_key = (rate, loss, profile)
        ci = ci_rows.get(ci_key, {})
        out.append(
            {
                "rate_bps": rate,
                "loss_rate": loss,
                "profile": profile,
                "scheduling": sched,
                "n_seeds": len(samples),
                "p0_within_deadline_mean": statistics.mean(p0_vals) if p0_vals else float("nan"),
                "p0_within_deadline_median": statistics.median(p0_vals) if p0_vals else float("nan"),
                "goodput_bps_mean": statistics.mean(gp_vals) if gp_vals else float("nan"),
                "censored_count_mean": statistics.mean(cens) if cens else 0.0,
                "paired_diff_ci_low": ci.get("paired_diff_ci_low", ""),
                "paired_diff_ci_high": ci.get("paired_diff_ci_high", ""),
            }
        )
    return out


def write_m3_artifacts(out_dir: Path, rows: list[dict[str, Any]]) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    raw = out_dir / RAW_NAME
    fieldnames = sorted({k for r in rows for k in r.keys()})
    with raw.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fieldnames)
        w.writeheader()
        w.writerows(rows)

    buf = io.StringIO()
    w = csv.DictWriter(buf, fieldnames=fieldnames)
    w.writeheader()
    w.writerows(rows)
    (out_dir / GZIP_NAME).write_bytes(gzip.compress(buf.getvalue().encode("utf-8"), mtime=0))

    cells = aggregate_m3_cells(rows)
    cell_fields = sorted({k for r in cells for k in r.keys()})
    with (out_dir / CELLS_NAME).open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=cell_fields)
        w.writeheader()
        w.writerows(cells)
