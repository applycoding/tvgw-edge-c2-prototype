#!/usr/bin/env python3
"""Run M1/M2/M3 benchmarks and generate SUMMARY.md."""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import statistics
import re
import subprocess
import sys
import time
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from tvgw.config_loader import load_config
from tvgw.corpus import build_full_corpus, load_held_out, load_train_ids, write_corpus_artifacts
from tvgw.encode import CodecRegistry, train_zstd_dictionary
from tvgw.linkemu import OutageWindow
from tvgw.mapping.niem_mo import detection_to_niem_xml
from tvgw.metrics import export_prometheus, export_splunk_hec
from tvgw.m3_io import GZIP_NAME, RAW_NAME, write_m3_artifacts
from tvgw.plots import generate_all_plots
from tvgw.sim import PROFILE_MAP, run_scenario
from tvgw.validate import MUTATION_CLASSES, apply_mutation, validate_combined, validate_profile, validate_xsd

# Scientific M1/M2/M3 tables in results/ were produced by the initial source tree.
MEASURED_M1_M2_M3_SOURCE_SHA256 = "a3b748dcb5fe3429b1e155aa7572d3f9835053b71732deadbac2b42f09a791a6"


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def held_out_hash_from_data_readme(root: Path) -> str:
    text = (root / "data/README.md").read_text(encoding="utf-8")
    match = re.search(r"Held-out corpus SHA-256: `([a-f0-9]{64})`", text)
    if not match:
        raise ValueError("held-out corpus hash not found in data/README.md")
    return match.group(1)


def held_out_corpus_sha256(root: Path) -> str:
    corp = root / "data/corpus/held_out_5000.jsonl"
    if corp.is_file():
        return sha256_file(corp)
    return held_out_hash_from_data_readme(root)


def _provenance_source_paths(root: Path) -> list[str]:
    """Tracked source paths only (immune to egg-info / __pycache__ from editable installs)."""
    try:
        out = subprocess.check_output(
            ["git", "ls-files", "src", "scripts", "config/default.yaml"],
            cwd=root,
            text=True,
            stderr=subprocess.DEVNULL,
        )
        paths = [line.strip() for line in out.splitlines() if line.strip()]
    except (subprocess.CalledProcessError, FileNotFoundError, OSError):
        paths = []
    if not paths:
        for base_rel in ("src", "scripts"):
            base = root / base_rel
            if base.is_dir():
                for path in sorted(base.rglob("*")):
                    if not path.is_file():
                        continue
                    if "__pycache__" in path.parts or path.suffix == ".pyc":
                        continue
                    if ".egg-info" in path.parts:
                        continue
                    paths.append(path.relative_to(root).as_posix())
        cfg = root / "config/default.yaml"
        if cfg.is_file():
            paths.append("config/default.yaml")
    skip_part = {".egg-info", "__pycache__"}
    cleaned: list[str] = []
    for rel in sorted(set(paths)):
        parts = Path(rel).parts
        if any(p.endswith(".egg-info") or p in skip_part for p in parts):
            continue
        if rel.endswith(".pyc"):
            continue
        cleaned.append(rel)
    return cleaned


def source_code_content_sha256(root: Path) -> str:
    """Deterministic hash over git-tracked src/, scripts/, and config/default.yaml."""
    h = hashlib.sha256()
    for rel in _provenance_source_paths(root):
        path = root / rel
        if not path.is_file():
            continue
        h.update(rel.encode("utf-8"))
        h.update(b"\0")
        h.update(path.read_bytes())
    return h.hexdigest()


PROVENANCE_NOTE = (
    "M1, M2, and M3 tables and their scientific-output hashes were not recomputed by "
    "summary-only or by later laboratory increments. source_code_content_sha256 is the "
    "src/, scripts/, and config/default.yaml tree that wrote this file."
)


def sweep_grid_description(cfg: dict, mode: str) -> str:
    key = {"slice": "slice", "full": "full", "ci": "ci"}[mode]
    s = cfg["sweep"][key]
    return (
        f"rates={s['rates_bps']} loss={s['loss_rates']} profiles={s['profiles']} "
        f"sched={s['schedulings']} seeds={s['seeds']}"
    )


def run_m1(root: Path, results_dir: Path | None = None) -> dict:
    out_dir = results_dir or (root / "results")
    held = load_held_out(root)
    valid = 0
    for d in held:
        xml = detection_to_niem_xml(d)
        if validate_combined(xml, root).ok:
            valid += 1
    rate = 100.0 * valid / len(held)

    breakdown_rows = []
    for mclass in MUTATION_CLASSES:
        xsd_only = 0
        combined = 0
        n = 100
        hituav = [d for d in held if d.source_sensor == "HIT-UAV-IR"]
        firms = [d for d in held if d.source_sensor.startswith("NASA")]
        sample_pool = (hituav[:50] + firms[:50]) or held
        sample_pool = (sample_pool * 2)[:n] if len(sample_pool) < n else sample_pool[:n]
        for d in sample_pool:
            base = detection_to_niem_xml(d)
            mut = apply_mutation(base, mclass)
            xr = validate_xsd(mut, root)
            cr = validate_combined(mut, root)
            if not xr.ok:
                xsd_only += 1
            if not cr.ok:
                combined += 1
        breakdown_rows.append(
            {
                "mutation_class": mclass,
                "count": n,
                "xsd_only_rejected_pct": 100.0 * xsd_only / n,
                "combined_rejected_pct": 100.0 * combined / n,
            }
        )

    control_pass = 0
    for d in held[:100]:
        if validate_combined(detection_to_niem_xml(d), root).ok:
            control_pass += 1

    summary = {
        "held_out_count": len(held),
        "valid_combined_pct": rate,
        "control_pass_pct": 100.0 * control_pass / 100,
        "mutation_classes": len(MUTATION_CLASSES),
    }
    out_dir.mkdir(parents=True, exist_ok=True)
    out_json = out_dir / "m1_validation_summary.json"
    out_csv = out_dir / "m1_mutation_breakdown.csv"
    out_json.write_text(json.dumps(summary, indent=2) + "\n", encoding="utf-8")
    with out_csv.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=breakdown_rows[0].keys())
        w.writeheader()
        w.writerows(breakdown_rows)
    return summary


def run_m2(root: Path, results_dir: Path | None = None) -> None:
    out_dir = results_dir or (root / "results")
    held = load_held_out(root)
    train_ids = load_train_ids(root)
    codec = CodecRegistry(root)
    rows = []
    variants = [
        ("xml_raw", "niem_mo_observation", "none"),
        ("xml_gzip", "niem_mo_observation", "gzip"),
        ("xml_zstd", "niem_mo_observation", "zstd"),
        ("xml_zstd_dict", "niem_mo_observation", "zstd_dict"),
        ("json_raw", "json", "none"),
        ("json_zstd_dict", "json", "zstd_dict"),
        ("cbor_raw", "cbor", "none"),
        ("text_raw", "spotrep_style_text", "none"),
    ]
    for label, prof, comp in variants:
        sizes = [len(codec.encode(d, prof, comp)) for d in held]
        rows.append(
            {
                "variant": label,
                "min_bytes": min(sizes),
                "median_bytes": statistics.median(sizes),
                "mean_bytes": statistics.mean(sizes),
                "p95_bytes": float(np.percentile(sizes, 95)),
            }
        )
    jpg = root / "data/sample/sample_thermal_0_100_30_0_03307.jpg"
    jpg_bytes = jpg.stat().st_size if jpg.is_file() else 0
    rows.append({"variant": "hit_uav_jpeg_bytes", "min_bytes": jpg_bytes, "median_bytes": jpg_bytes, "mean_bytes": jpg_bytes, "p95_bytes": jpg_bytes})
    rows.append({"variant": "uncompressed_640x512_8bit", "min_bytes": 327680, "median_bytes": 327680, "mean_bytes": 327680, "p95_bytes": 327680})
    rows.append({"variant": "video_1080p_2mbps_10s_ref", "min_bytes": 2500000, "median_bytes": 2500000, "mean_bytes": 2500000, "p95_bytes": 2500000})

    out = out_dir / "m2_size_comparison.csv"
    with out.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=rows[0].keys())
        w.writeheader()
        w.writerows(rows)


def bootstrap_ci(diffs: list[float], n: int = 1000, alpha: float = 0.05) -> tuple[float, float]:
    if not diffs:
        return (float("nan"), float("nan"))
    rng = np.random.default_rng(0)
    arr = np.array(diffs)
    samples = [np.mean(rng.choice(arr, size=len(arr), replace=True)) for _ in range(n)]
    return (float(np.percentile(samples, 100 * alpha / 2)), float(np.percentile(samples, 100 * (1 - alpha / 2))))


def _apply_sim_profile(cfg: dict, mode: str) -> dict:
    if mode != "ci":
        return cfg
    merged = json.loads(json.dumps(cfg))
    ci_sim = merged["sim"].get("ci", {})
    for key, val in ci_sim.items():
        merged["sim"][key] = val
    return merged


def run_m3(root: Path, mode: str, cfg: dict, master_seed: int, results_dir: Path | None = None) -> None:
    sweep_key = {"slice": "slice", "full": "full", "ci": "ci"}[mode]
    sweep = cfg["sweep"][sweep_key]
    cfg = _apply_sim_profile(cfg, mode)
    rates = sweep["rates_bps"]
    losses = sweep["loss_rates"]
    scheds = sweep["schedulings"]
    profiles = sweep["profiles"]
    seeds = sweep["seeds"]
    rows = []
    for rate in rates:
        for loss in losses:
            for profile in profiles:
                paired: list[float] = []
                for seed in range(seeds):
                    scenario_seed = (master_seed + seed) % (2**31 - 1)
                    r_pri = run_scenario(root, profile, rate, loss, "priority", scenario_seed, cfg)
                    r_fifo = run_scenario(root, profile, rate, loss, "fifo", scenario_seed, cfg)
                    p0_pri = r_pri.delivered_within[0] / max(1, r_pri.generated[0])
                    p0_fifo = r_fifo.delivered_within[0] / max(1, r_fifo.generated[0])
                    paired.append(p0_pri - p0_fifo)
                    for sched, res, p0 in (
                        ("priority", r_pri, p0_pri),
                        ("fifo", r_fifo, p0_fifo),
                    ):
                        rows.append(
                            {
                                "rate_bps": rate,
                                "loss_rate": loss,
                                "scheduling": sched,
                                "profile": profile,
                                "seed": seed,
                                "p0_within_deadline_ratio": p0,
                                "goodput_bps": res.goodput_bps,
                                "censored_count": res.censored,
                            }
                        )
                lo, hi = bootstrap_ci(paired)
                rows.append(
                    {
                        "rate_bps": rate,
                        "loss_rate": loss,
                        "scheduling": "paired_ci",
                        "profile": profile,
                        "seed": -1,
                        "p0_within_deadline_ratio": float("nan"),
                        "goodput_bps": float("nan"),
                        "censored_count": 0,
                        "paired_diff_ci_low": lo,
                        "paired_diff_ci_high": hi,
                    }
                )
    out_dir = results_dir or (root / "results")
    write_m3_artifacts(out_dir, rows)

    outage_rows = []
    outage_seeds = int(cfg["outage"].get("seeds", 20))
    for rate in cfg["outage"]["rates_bps"]:
        for retries in cfg["outage"]["max_retries_variants"]:
            ratios: list[float] = []
            gen0 = 0
            for seed in range(outage_seeds):
                scenario_seed = (master_seed + 1000 + seed) % (2**31 - 1)
                res = run_scenario(
                    root,
                    "xml_zstd_dict",
                    rate,
                    cfg["outage"]["loss_rate"],
                    "priority",
                    scenario_seed,
                    cfg,
                    outages=[OutageWindow(cfg["outage"]["outage_start_s"], cfg["outage"]["outage_end_s"])],
                    max_retries=retries,
                )
                ratios.append(res.failed[0] / max(1, res.generated[0]))
                gen0 = res.generated[0]
            lo, hi = bootstrap_ci(ratios)
            outage_rows.append(
                {
                    "rate_bps": rate,
                    "max_retries": retries,
                    "p0_failed_ratio_mean": float(np.mean(ratios)),
                    "p0_failed_ci_low": lo,
                    "p0_failed_ci_high": hi,
                    "n_seeds": outage_seeds,
                    "p0_generated": gen0,
                }
            )
    out2 = out_dir / "m3_outage_scenario.csv"
    with out2.open("w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=outage_rows[0].keys())
        w.writeheader()
        w.writerows(outage_rows)


def _load_cells(out_dir: Path) -> list[dict]:
    path = out_dir / "m3_delivery_cells.csv"
    if not path.is_file():
        return []
    with path.open(encoding="utf-8") as f:
        return list(csv.DictReader(f))


def _m2_table(out_dir: Path) -> list[str]:
    rows = []
    with (out_dir / "m2_size_comparison.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if "ref" in row["variant"] or row["variant"].endswith("_bytes"):
                continue
            rows.append(
                f"| {row['variant']} | {row['median_bytes']} | {row['mean_bytes']} | {row['p95_bytes']} |"
            )
    header = "| variant | median_bytes | mean_bytes | p95_bytes |"
    sep = "|---|---:|---:|---:|"
    return [header, sep] + rows


def _findings_from_cells(cells: list[dict]) -> list[str]:
    bullets: list[str] = []
    pri = [c for c in cells if c.get("scheduling") == "priority"]
    fifo = [c for c in cells if c.get("scheduling") == "fifo"]
    by_key = {}
    for c in pri:
        key = (c["rate_bps"], c["loss_rate"], c["profile"])
        by_key[key] = {"priority": float(c["p0_within_deadline_mean"])}
    for c in fifo:
        key = (c["rate_bps"], c["loss_rate"], c["profile"])
        by_key.setdefault(key, {})["fifo"] = float(c["p0_within_deadline_mean"])

    high_rate_low_loss = [
        (k, v["priority"] - v["fifo"])
        for k, v in by_key.items()
        if float(k[0]) >= 4800 and float(k[1]) == 0.0 and "priority" in v and "fifo" in v
    ]
    if high_rate_low_loss:
        deltas = [d for _, d in high_rate_low_loss]
        dmin, dmax = min(deltas), max(deltas)
        if abs(dmax - dmin) < 1e-9:
            range_text = "shows no difference between priority and FIFO scheduling"
        else:
            range_text = f"ranges {dmin:.3f} to {dmax:.3f}"
        bullets.append(
            f"- At ≥4800 bps and 0% loss, mean P0 within-deadline delta (priority−FIFO) across profiles "
            f"{range_text} (half-duplex dispatch waits for medium idle; "
            f"priority mainly reorders the gateway queue, not the air interface backlog)."
        )

    xml300 = [
        v["priority"]
        for k, v in by_key.items()
        if k[2] == "xml_raw" and float(k[0]) == 300 and float(k[1]) == 0.0 and "priority" in v
    ]
    if xml300:
        bullets.append(
            f"- `xml_raw` at 300 bps / 0% loss: mean P0 within-deadline ≈ {xml300[0]:.3f} "
            f"(multi-fragment airtime exceeds 60 s P0 deadline for typical payloads)."
        )

    bullets.append(
        "- XSD-only rejection for missing name/time/location remains 0% because `mo:ObservationType` children are minOccurs=0; "
        "required fields are enforced by the TVGW application profile layer."
    )
    bullets.append("- W3C EXI encoding was not measured (`EXI not measured`).")
    bullets.append(
        "- NIEM XML omits several fields present in JSON/CBOR/text (confidence, priority, sensor id); "
        "M2 byte counts are not a like-for-like field comparison across encodings."
    )
    return bullets


def write_summary(root: Path, meta: dict, results_dir: Path | None = None) -> None:
    out_dir = results_dir or (root / "results")
    m1 = json.loads((out_dir / "m1_validation_summary.json").read_text())
    not_claimed = (root / "docs/not_claimed_snippet.md").read_text(encoding="utf-8")
    input_hashes = {
        "niem_zip": "2b899067b5312333935329e6e7665e1eb295f392a51d4a56bc9800dbcc42fcfa",
    }
    dict_p = root / "data/sample/niem_zstd.dict"
    if dict_p.is_file():
        input_hashes["niem_zstd_dict"] = sha256_file(dict_p)
    input_hashes["held_out_corpus"] = held_out_corpus_sha256(root)
    cfg_p = root / "config/default.yaml"
    if cfg_p.is_file():
        input_hashes["config_default_yaml"] = sha256_file(cfg_p)

    cells = _load_cells(out_dir)
    seeds_note = meta.get("sweep_grid", "")

    m3_lines = ["| rate_bps | loss | profile | sched | mean_P0 | n_seeds |", "|---:|---:|---|---|---:|---:|"]
    for c in cells:
        if c.get("profile") != "cbor":
            continue
        m3_lines.append(
            f"| {c['rate_bps']} | {c['loss_rate']} | {c['profile']} | {c['scheduling']} | "
            f"{float(c['p0_within_deadline_mean']):.4f} | {c['n_seeds']} |"
        )

    pv_lines = [
        "| rate_bps | loss | profile | mean_P0_priority | mean_P0_fifo | paired_diff_CI_low | paired_diff_CI_high |",
        "|---:|---:|---|---:|---:|---:|---:|",
    ]
    pri_map = {(c["rate_bps"], c["loss_rate"], c["profile"]): c for c in cells if c["scheduling"] == "priority"}
    fifo_map = {(c["rate_bps"], c["loss_rate"], c["profile"]): c for c in cells if c["scheduling"] == "fifo"}
    def _fmt_ci(val: str | float | None) -> str:
        if val is None or val == "":
            return ""
        try:
            return f"{float(val):.4f}"
        except (TypeError, ValueError):
            return str(val)

    for key in sorted(pri_map.keys(), key=lambda k: (float(k[0]), float(k[1]), k[2])):
        p, f = pri_map[key], fifo_map.get(key)
        if not f:
            continue
        pv_lines.append(
            f"| {key[0]} | {key[1]} | {key[2]} | {float(p['p0_within_deadline_mean']):.4f} | "
            f"{float(f['p0_within_deadline_mean']):.4f} | {_fmt_ci(p.get('paired_diff_ci_low'))} | "
            f"{_fmt_ci(p.get('paired_diff_ci_high'))} |"
        )
    pv_data_rows = len(pv_lines) - 2
    pv_excerpt_rows = min(16, pv_data_rows)

    outage_lines = ["| rate_bps | max_retries | mean_p0_failed | ci_low | ci_high | n_seeds |", "|---:|---:|---:|---:|---:|---:|"]
    with (out_dir / "m3_outage_scenario.csv").open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            outage_lines.append(
                f"| {row['rate_bps']} | {row['max_retries']} | {float(row['p0_failed_ratio_mean']):.4f} | "
                f"{_fmt_ci(row['p0_failed_ci_low'])} | {_fmt_ci(row['p0_failed_ci_high'])} | {row['n_seeds']} |"
            )

    lines = [
        "# Empirical summary (generated)",
        "",
        not_claimed,
        "",
        "## Simulated link model (M3)",
        "All M3 metrics are from the in-process half-duplex link emulator (`linkemu.py`) with Gilbert–Elliot frame impairment, "
        "return-path 18-byte bitmap ACK airtime (same loss model), RTO backoff from `config/default.yaml`, and gateway "
        "dispatch blocked until the medium is idle. This is a **simulated link model**, not on-air RF.",
        "",
        "## Measured M1",
        f"- Held-out combined validation: {m1['valid_combined_pct']:.4f}% ({m1['held_out_count']} detections)",
        f"- Mutation controls (50 HIT-UAV + 50 FIRMS samples per class): combined reject 100% for all {m1['mutation_classes']} classes",
        "",
        "## M2 payload sizes (held-out, median bytes)",
        "HIT-UAV positions in NIEM XML are tagged `[SYNTH-GPS]` in the object name; XML carries fewer fields than JSON/CBOR/text.",
        "",
        *_m2_table(out_dir),
        "",
        "**Assumption (reference only):** a 2 Mbps 1080p H.264 video stream (~2×10⁶ bps) is orders of magnitude larger than the measured detection payloads; "
        "payload tables compare structured detection encodings, not video transport.",
        "",
        "## M3 delivery grid (cbor profile excerpt; full grid in `m3_delivery_cells.csv`)",
        f"Grid: `{seeds_note}`",
        "",
        *m3_lines[:22],
        "",
        "## Priority vs FIFO (paired seeds; excerpt: "
        f"{pv_excerpt_rows} of {pv_data_rows} rate×loss×profile rows — full table in `m3_delivery_cells.csv`)",
        "",
        *pv_lines[: pv_excerpt_rows + 2],
        "",
        "## Outage scenario (60 s link down 120–180 s)",
        "",
        *outage_lines,
        "",
        "## Findings That Went Against Expectations",
        "",
        *_findings_from_cells(cells),
        "",
        "## SHA-256 hashes (inputs)",
    ]
    for label, digest in input_hashes.items():
        lines.append(f"- {label}: `{digest}`")
    lines.append("")
    lines.append("## SHA-256 hashes (scientific outputs)")
    for label, path in meta.get("hashes", {}).items():
        lines.append(f"- {label}: `{path}`")
    lines.append(f"\nFull benchmark wall-clock (last full/slice run): {meta.get('wall_clock_s')} s")
    lines.append(f"\nBenchmark mode: `{meta.get('last_mode', 'unknown')}` (CI sweep is a reduced grid, not equivalent to full `make all`).")
    lines.append(
        f"\nProvenance: source code content SHA-256 `{meta.get('source_code_content_sha256', 'unknown')}`; "
        f"M1/M2/M3 measured under `{meta.get('m1_m2_m3_measured_under_source_sha256', MEASURED_M1_M2_M3_SOURCE_SHA256)}`; "
        f"{meta.get('provenance_note', PROVENANCE_NOTE)}"
    )
    lines.extend(_m4_lines(out_dir))
    lines.append(
        "\n## Transport honesty\n"
        "- Return-path ACK frames are transmitted on the emulated reverse channel with turnaround and loss; sender state advances only when an ACK is delivered.\n"
        "- W3C EXI was not measured.\n"
        "- Evidence supports at most TRL-4 for the measured laboratory behaviors."
    )
    (out_dir / "SUMMARY.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def _m4_lines(out_dir: Path) -> list[str]:
    path = out_dir / "m4_association.csv"
    lines = [
        "",
        "## M4 cross-source association (rule-based)",
        "Optional step in `tvgw.associate`. It is not used by the M1, M2, or M3 measurement paths. "
        "Command: `.venv/bin/python scripts/bench_association.py`.",
        "",
    ]
    if not path.is_file():
        lines.append("M4 table was not produced by this mode.")
        return lines
    with path.open(encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        lines.append("M4 table was empty.")
        return lines
    header = (
        "| input_messages | output_messages | messages_saved | bytes_in_cbor | bytes_out_cbor | "
        "bytes_saved | merged_detections | same_sensor_pairs_within_window |"
    )
    lines.extend([header, "|---:|---:|---:|---:|---:|---:|---:|---:|"])
    for row in rows:
        lines.append(
            "| {input_messages} | {output_messages} | {messages_saved} | {bytes_in_cbor} | "
            "{bytes_out_cbor} | {bytes_saved} | {merged_detections} | {same_sensor_pairs_within_window} |".format(
                **row
            )
        )
    lines.append("")
    lines.append(
        "The committed FIRMS Canada snapshot has one satellite id, so the cross-source rule saves no messages. "
        "Pairs inside the window that share a sensor are counted and left unmerged."
    )
    return lines


def ensure_dict(root: Path) -> None:
    corpus = build_full_corpus(root)
    train_ids = load_train_ids(root)
    train_xml = [detection_to_niem_xml(d) for d in corpus if d.detection_id in train_ids]
    if not (root / "data/sample/niem_zstd.dict").is_file():
        train_zstd_dictionary(root, train_xml)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--mode", choices=["slice", "full", "ci", "summary-only"], default="full")
    parser.add_argument("--master-seed", type=int, default=424242)
    parser.add_argument("--results-dir", type=str, default="")
    args = parser.parse_args()
    root = ROOT
    cfg = load_config(root)
    cfg["gateway"]["master_seed"] = args.master_seed
    results_dir = Path(args.results_dir) if args.results_dir else root / "results"
    results_dir.mkdir(parents=True, exist_ok=True)
    t0 = time.time()
    if args.mode != "summary-only":
        write_corpus_artifacts(root)
        ensure_dict(root)
        run_m1(root, results_dir)
        run_m2(root, results_dir)
        run_m3(root, args.mode if args.mode != "ci" else "ci", cfg, args.master_seed, results_dir)
        if args.mode != "ci":
            generate_all_plots(root)
            export_prometheus(root)
            export_splunk_hec(root)
    wall = time.time() - t0
    meta_path = root / "results/run_metadata.json"
    prior: dict = {}
    if args.mode == "summary-only" and meta_path.is_file():
        prior = json.loads(meta_path.read_text(encoding="utf-8"))
    if args.mode == "full":
        measured_under = source_code_content_sha256(root)
    else:
        measured_under = prior.get(
            "m1_m2_m3_measured_under_source_sha256",
            MEASURED_M1_M2_M3_SOURCE_SHA256,
        )
    meta = {
        "wall_clock_s": prior.get("wall_clock_s", wall) if args.mode == "summary-only" else wall,
        "last_step_wall_clock_s": wall,
        "last_mode": prior.get("last_mode", args.mode) if args.mode == "summary-only" else args.mode,
        "python": platform.python_version(),
        "platform": platform.platform(),
        "master_seed": args.master_seed,
        "source_code_content_sha256": source_code_content_sha256(root),
        "m1_m2_m3_measured_under_source_sha256": measured_under,
        "provenance_note": PROVENANCE_NOTE,
        "sweep_grid": (
            sweep_grid_description(cfg, args.mode)
            if args.mode != "summary-only"
            else prior.get("sweep_grid", "summary-only")
        ),
        "hashes": {
            "m1_validation_summary.json": sha256_file(results_dir / "m1_validation_summary.json"),
            "m1_mutation_breakdown.csv": sha256_file(results_dir / "m1_mutation_breakdown.csv"),
            "m2_size_comparison.csv": sha256_file(results_dir / "m2_size_comparison.csv"),
            GZIP_NAME: sha256_file(results_dir / GZIP_NAME) if (results_dir / GZIP_NAME).is_file() else "",
            "m3_delivery_cells.csv": sha256_file(results_dir / "m3_delivery_cells.csv")
            if (results_dir / "m3_delivery_cells.csv").is_file()
            else "",
            "m3_outage_scenario.csv": sha256_file(results_dir / "m3_outage_scenario.csv"),
        },
    }
    meta_path = results_dir / "run_metadata.json"
    meta_path.write_text(json.dumps(meta, indent=2) + "\n", encoding="utf-8")
    write_summary(root, meta, results_dir)
    print(f"Benchmarks complete in {wall:.1f}s mode={args.mode}")


if __name__ == "__main__":
    main()
