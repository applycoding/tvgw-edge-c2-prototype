"""Matplotlib plot generation from measured benchmark CSVs."""

from __future__ import annotations

import csv
from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np

from tvgw.config_loader import load_config
from tvgw.linkemu import OutageWindow
from tvgw.m3_io import iter_m3_run_rows
from tvgw.sim import run_scenario


def generate_all_plots(root: Path | None = None) -> None:
    root = root or Path(__file__).resolve().parents[2]
    plots = root / "results/plots"
    plots.mkdir(parents=True, exist_ok=True)
    _plot_m2(root, plots)
    _plot_m3_delivery(root, plots)
    _plot_m3_latency(root, plots)
    _plot_m3_outage_timeline(root, plots)


def _cells_path(root: Path) -> Path:
    return root / "results/m3_delivery_cells.csv"


def _plot_m2(root: Path, plots: Path) -> None:
    m2_path = root / "results/m2_size_comparison.csv"
    if not m2_path.is_file():
        return
    variants, medians = [], []
    with m2_path.open(encoding="utf-8") as f:
        for row in csv.DictReader(f):
            if row["variant"].endswith("_bytes") or "ref" in row["variant"]:
                continue
            variants.append(row["variant"])
            medians.append(float(row["median_bytes"]))
    fig, ax = plt.subplots(figsize=(10, 5))
    ax.bar(variants, medians, color="steelblue")
    ax.set_ylabel("Median payload size (bytes)")
    ax.set_xlabel("Codec / compression variant")
    ax.set_title("M2 held-out payload sizes")
    plt.xticks(rotation=45, ha="right")
    fig.tight_layout()
    fig.savefig(plots / "m2_payload_sizes.png", dpi=120)
    plt.close(fig)


def _plot_m3_delivery(root: Path, plots: Path) -> None:
    cells = _cells_path(root)
    if cells.is_file():
        losses, means = [], []
        with cells.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("scheduling") != "priority":
                    continue
                if row.get("profile") != "cbor":
                    continue
                if row.get("rate_bps") != "1200":
                    continue
                losses.append(float(row["loss_rate"]) * 100)
                means.append(float(row["p0_within_deadline_mean"]))
        if losses:
            order = np.argsort(losses)
            losses = [losses[i] for i in order]
            means = [means[i] for i in order]
            fig, ax = plt.subplots(figsize=(8, 5))
            ax.plot(losses, means, marker="o")
            ax.set_xlabel("Frame impairment rate (%)")
            ax.set_ylabel("Mean P0 within-deadline delivery ratio")
            ax.set_title("M3 delivery vs loss @ 1200 bps (cbor, priority)")
            ax.set_ylim(0, 1.05)
            fig.tight_layout()
            fig.savefig(plots / "m3_delivery_vs_loss.png", dpi=120)
            plt.close(fig)
            return

    rows = list(iter_m3_run_rows(root / "results"))
    if not rows:
        return
    buckets: dict[float, list[float]] = {}
    for row in rows:
        if row.get("scheduling") != "priority" or row.get("profile") != "cbor":
            continue
        if row.get("rate_bps") != "1200" or row.get("seed") == "-1":
            continue
        lr = float(row["loss_rate"])
        buckets.setdefault(lr, []).append(float(row["p0_within_deadline_ratio"]))
    if not buckets:
        return
    losses = sorted(buckets)
    means = [float(np.mean(buckets[l])) for l in losses]
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot([l * 100 for l in losses], means, marker="o")
    ax.set_xlabel("Frame impairment rate (%)")
    ax.set_ylabel("Mean P0 within-deadline delivery ratio")
    ax.set_title("M3 delivery vs loss @ 1200 bps (cbor, priority)")
    fig.tight_layout()
    fig.savefig(plots / "m3_delivery_vs_loss.png", dpi=120)
    plt.close(fig)


def _plot_m3_latency(root: Path, plots: Path) -> None:
    cells = _cells_path(root)
    rates: list[int] = []
    pri_gp: list[float] = []
    fifo_gp: list[float] = []
    if cells.is_file():
        data_pri: dict[int, list[float]] = {}
        data_fifo: dict[int, list[float]] = {}
        with cells.open(encoding="utf-8") as f:
            for row in csv.DictReader(f):
                if row.get("loss_rate") != "0.0" or row.get("profile") != "cbor":
                    continue
                rate = int(row["rate_bps"])
                val = float(row["goodput_bps_mean"])
                if row["scheduling"] == "priority":
                    data_pri.setdefault(rate, []).append(val)
                elif row["scheduling"] == "fifo":
                    data_fifo.setdefault(rate, []).append(val)
        rates = sorted(set(data_pri) | set(data_fifo))
        pri_gp = [float(np.mean(data_pri.get(r, [0]))) for r in rates]
        fifo_gp = [float(np.mean(data_fifo.get(r, [0]))) for r in rates]
    else:
        data_pri = {}
        data_fifo = {}
        for row in iter_m3_run_rows(root / "results"):
            if row.get("loss_rate") != "0.0" or row.get("profile") != "cbor" or row.get("seed") == "-1":
                continue
            rate = int(row["rate_bps"])
            val = float(row.get("goodput_bps", 0))
            if row["scheduling"] == "priority":
                data_pri.setdefault(rate, []).append(val)
            elif row["scheduling"] == "fifo":
                data_fifo.setdefault(rate, []).append(val)
        rates = sorted(set(data_pri) | set(data_fifo))
        pri_gp = [float(np.mean(data_pri.get(r, [0]))) for r in rates]
        fifo_gp = [float(np.mean(data_fifo.get(r, [0]))) for r in rates]

    if not rates:
        return
    fig, ax = plt.subplots(figsize=(8, 5))
    ax.plot(rates, pri_gp, marker="s", label="priority mean goodput")
    ax.plot(rates, fifo_gp, marker="^", label="fifo mean goodput")
    ax.set_xlabel("Link rate (bps)")
    ax.set_ylabel("Goodput (bits/s)")
    ax.set_title("M3 goodput vs rate (0% loss, cbor)")
    ax.legend()
    fig.tight_layout()
    fig.savefig(plots / "m3_latency_vs_rate.png", dpi=120)
    plt.close(fig)


def _plot_m3_outage_timeline(root: Path, plots: Path) -> None:
    cfg = load_config(root)
    trace: list[dict] = []
    outages = [
        OutageWindow(cfg["outage"]["outage_start_s"], cfg["outage"]["outage_end_s"]),
    ]
    run_scenario(
        root,
        "xml_zstd_dict",
        600,
        cfg["outage"]["loss_rate"],
        "priority",
        42,
        cfg,
        outages=outages,
        trace=trace,
    )
    if not trace:
        return
    t = [p["t_s"] for p in trace]
    q = [p["queue_depth"] for p in trace]
    deliv = [p["delivered_cum"] for p in trace]
    fig, ax1 = plt.subplots(figsize=(10, 5))
    ax1.plot(t, q, label="Queue depth (messages)", color="tab:blue")
    ax1.set_xlabel("Scenario virtual time (s)")
    ax1.set_ylabel("Queue depth (messages)")
    ax2 = ax1.twinx()
    ax2.plot(t, deliv, label="Cumulative deliveries", color="tab:green", alpha=0.8)
    ax2.set_ylabel("Cumulative deliveries (count)")
    ax1.axvspan(cfg["outage"]["outage_start_s"], cfg["outage"]["outage_end_s"], color="red", alpha=0.15)
    ax1.set_title("M3 outage scenario timeline @ 600 bps")
    ax1.legend(loc="upper left")
    fig.tight_layout()
    fig.savefig(plots / "m3_outage_timeline.png", dpi=120)
    plt.close(fig)
