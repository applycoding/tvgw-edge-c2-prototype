"""Seeded scenario generator and paired simulation runner."""

from __future__ import annotations

import struct
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Dict, List

import numpy as np

from tvgw.encode import CodecRegistry
from tvgw.fragment import WireFrame, build_ack_frame, fragment_payload
from tvgw.linkemu import LinkEmulator, OutageWindow
from tvgw.metrics_live import LiveMetrics
from tvgw.models import Detection, Priority, deadline_s
from tvgw.priority import PriorityQueue, QueuedMessage


@dataclass
class SimResult:
    delivered_within: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    delivered_late: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    failed: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    expired: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    dropped_incoming: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    dropped_duplicate_id: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    generated: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    admitted: Dict[int, int] = field(default_factory=lambda: {0: 0, 1: 0, 2: 0})
    latencies: List[float] = field(default_factory=list)
    latencies_by_priority: Dict[int, List[float]] = field(default_factory=lambda: {0: [], 1: [], 2: []})
    censored: int = 0
    goodput_bps: float = 0.0
    link_busy_end_s: float = 0.0
    total_frames_tx: int = 0
    arq_retransmissions: int = 0
    ack_frames_tx: int = 0
    crc_errors_detected: int = 0
    total_virtual_time_s: float = 0.0
    delivered_bytes: int = 0


PROFILE_MAP = {
    "xml_raw": ("niem_mo_observation", "none", 0x01),
    "xml_zstd_dict": ("niem_mo_observation", "zstd_dict", 0x31),
    "cbor": ("cbor", "none", 0x04),
    "text": ("spotrep_style_text", "none", 0x02),
    "json": ("json", "none", 0x03),
}


def _link_from_cfg(rate_bps: float, loss: float, rng: np.random.Generator, cfg: dict, outages: List[OutageWindow]) -> LinkEmulator:
    lc = cfg.get("link", {})
    ge = lc.get("gilbert", {})
    return LinkEmulator(
        rate_bps,
        loss,
        rng,
        turnaround_s=float(lc.get("turnaround_s", 0.20)),
        prop_delay_s=float(lc.get("prop_delay_s", 0.05)),
        jitter_s=float(lc.get("jitter_s", 0.01)),
        preamble_bytes=int(lc.get("preamble_bytes", 4)),
        outages=outages,
        e_good=float(ge.get("e_good", 0.001)),
        e_bad=float(ge.get("e_bad", 0.80)),
        p_bg=float(ge.get("p_bg", 0.20)),
    )


def generate_arrivals(
    held_out: List[Detection],
    seed: int,
    cfg: dict,
) -> List[tuple[float, Detection]]:
    rng = np.random.default_rng(seed)
    sim_cfg = cfg["sim"]
    window = sim_cfg["arrival_window_s"]
    events: List[tuple[float, Detection]] = []

    classes = [d for d in held_out]
    rng.shuffle(classes)
    times = sorted(rng.uniform(0, window, size=sim_cfg["background_count"]))
    for t, idx in zip(times, range(sim_cfg["background_count"])):
        det = classes[idx % len(classes)]
        events.append((float(t), det))

    burst_times = rng.uniform(sim_cfg["burst_start_s"], sim_cfg["burst_end_s"], size=sim_cfg["burst_count"])
    for t in burst_times:
        det = classes[int(rng.integers(0, len(classes)))]
        events.append((float(t), det))

    sample = classes[0] if classes else held_out[0]
    for i in range(sim_cfg["heartbeat_count"]):
        t = i * sim_cfg["heartbeat_interval_s"]
        hb = Detection(
            detection_id=f"HB_{seed}_{i}",
            timestamp_utc=datetime(2026, 10, 26, tzinfo=timezone.utc),
            source_sensor="SYS-TELEMETRY",
            domain=sample.domain,
            functional_service=sample.functional_service,
            object_class="heartbeat",
            confidence_score=0.1,
            latitude_deg=0.0,
            longitude_deg=0.0,
            priority=Priority.P2_ROUTINE,
        )
        events.append((float(t), hb))

    events.sort(key=lambda x: x[0])
    return events


def _bitmap_to_set(bitmap: int, total: int) -> set[int]:
    return {i for i in range(total) if (bitmap >> i) & 1}


def _set_to_bitmap(indices: set[int]) -> int:
    return sum(1 << i for i in indices)


def run_scenario(
    root: Path | str,
    profile_name: str,
    rate_bps: float,
    loss: float,
    scheduling: str,
    seed: int,
    cfg: dict,
    outages: List[OutageWindow] | None = None,
    max_retries: int | None = None,
    trace: List[dict] | None = None,
    metrics: LiveMetrics | None = None,
) -> SimResult:
    from tvgw.corpus import load_held_out

    root = Path(root)
    held = load_held_out(root)
    arrivals = generate_arrivals(held, seed, cfg)
    codec = CodecRegistry(root)
    prof, comp, pflags = PROFILE_MAP[profile_name]
    mtu = cfg["gateway"]["mtu_bytes"]
    arq_cfg = cfg["arq"]
    retries = max_retries if max_retries is not None else int(arq_cfg["max_retries"])
    horizon = cfg["sim"]["drain_horizon_s"]
    queue_max = int(cfg["gateway"].get("max_queue_messages", 100))

    rng_fwd = np.random.default_rng(seed + 1)
    link_fwd = _link_from_cfg(rate_bps, loss, rng_fwd, cfg, outages or [])
    pq = PriorityQueue(mode=scheduling, max_size=queue_max)
    result = SimResult()
    now = 0.0
    msg_seq = 0
    in_flight: dict | None = None
    delivered_cum = 0

    def encode_det(det: Detection) -> bytes:
        return codec.encode(det, prof, comp)

    def link_up(t: float) -> bool:
        for win in outages or []:
            if win.start_s <= t <= win.end_s:
                return False
        return True

    arrival_idx = 0
    step = 0.25
    while now < horizon:
        pq.virtual_now = now
        while arrival_idx < len(arrivals) and arrivals[arrival_idx][0] <= now:
            t, det = arrivals[arrival_idx]
            result.generated[det.priority_int] += 1
            payload = encode_det(det)
            msg = QueuedMessage(det, payload, t, 0, profile_name)
            if det.detection_id in pq.seen_ids:
                result.dropped_duplicate_id[det.priority_int] += 1
            elif pq.admit(msg):
                result.admitted[det.priority_int] += 1
            else:
                result.dropped_incoming[det.priority_int] += 1
            arrival_idx += 1

        if in_flight is None and now >= link_fwd.medium_free_at_s:
            head = pq.pop()
            if head is None and arrival_idx >= len(arrivals):
                break
            if head is not None:
                msg_seq = (msg_seq + 1) % 65536
                in_flight = {
                    "job": head,
                    "seq": msg_seq,
                    "attempt": 0,
                    "confirmed": set(),
                    "timer_end": None,
                    "frames": None,
                }
                _start_burst(
                    in_flight,
                    link_fwd,
                    mtu,
                    pflags,
                    result,
                    cfg,
                    max(now, link_fwd.medium_free_at_s),
                    metrics,
                )

        if in_flight and in_flight.get("done"):
            delivered_cum += 1
            in_flight = None
        elif in_flight and in_flight.get("timer_end") is not None and now >= in_flight["timer_end"]:
            if in_flight["attempt"] >= retries:
                pri = in_flight["job"].priority_int
                result.failed[pri] += 1
                in_flight = None
            else:
                in_flight["attempt"] += 1
                total = len(in_flight["frames"])
                missing = set(range(total)) - in_flight["confirmed"]
                result.arq_retransmissions += len(missing)
                _start_burst(
                    in_flight,
                    link_fwd,
                    mtu,
                    pflags,
                    result,
                    cfg,
                    max(now, link_fwd.medium_free_at_s),
                    metrics,
                )

        if trace is not None:
            trace.append(
                {
                    "t_s": now,
                    "queue_depth": len(pq.queue),
                    "link_up": link_up(now),
                    "delivered_cum": delivered_cum,
                    "medium_free_at_s": link_fwd.medium_free_at_s,
                }
            )
        _publish_metrics(metrics, now, pq, in_flight, link_fwd, result, outages)

        if arrival_idx >= len(arrivals) and in_flight is None and not pq.queue:
            if now >= link_fwd.medium_free_at_s:
                break
        now += step

    for pri, count in pq.expired_in_queue.items():
        result.expired[pri] += count

    result.total_virtual_time_s = max(now, link_fwd.medium_free_at_s)
    result.link_busy_end_s = link_fwd.medium_free_at_s
    delivered = sum(result.delivered_within.values()) + sum(result.delivered_late.values())
    total_gen = sum(result.generated.values())
    result.censored = total_gen - delivered - sum(result.failed.values()) - sum(result.expired.values()) - sum(
        result.dropped_incoming.values()
    ) - sum(result.dropped_duplicate_id.values())
    if result.link_busy_end_s > 0:
        result.goodput_bps = (result.delivered_bytes * 8) / result.link_busy_end_s
    result.crc_errors_detected = link_fwd.crc_errors_detected
    _publish_metrics(metrics, now, pq, in_flight, link_fwd, result, outages)
    return result


def _link_state_name(
    now: float,
    in_flight: dict | None,
    link: LinkEmulator,
    outages: List[OutageWindow] | None,
) -> str:
    for win in outages or []:
        if win.start_s <= now <= win.end_s:
            return "down"
    if in_flight is not None or now < link.medium_free_at_s:
        return "busy"
    return "idle"


def _publish_metrics(
    metrics: LiveMetrics | None,
    now: float,
    pq: PriorityQueue,
    in_flight: dict | None,
    link: LinkEmulator,
    result: SimResult,
    outages: List[OutageWindow] | None,
) -> None:
    if metrics is None:
        return
    metrics.observe(
        queue_depth=len(pq.queue),
        link_state=_link_state_name(now, in_flight, link, outages),
        retries=result.arq_retransmissions,
        failures=result.failed,
    )


def _start_burst(
    job_state: dict,
    link: LinkEmulator,
    mtu: int,
    pflags: int,
    result: SimResult,
    cfg: dict,
    start_s: float,
    metrics: LiveMetrics | None = None,
) -> None:
    job = job_state["job"]
    arq_cfg = cfg["arq"]
    if job_state.get("frames") is None:
        job_state["frames"] = fragment_payload(
            job.payload,
            job_state["seq"],
            pflags,
            job.priority_int,
            0,
            mtu=mtu,
        )
    frames = job_state["frames"]
    total = len(frames)
    confirmed: set[int] = set(job_state["confirmed"])
    missing = set(range(total)) - confirmed

    received_fwd: set[int] = set()

    def on_deliver(frame_bytes: bytes, _arr: float, frag_idx: int) -> None:
        try:
            WireFrame.unpack(frame_bytes)
            received_fwd.add(frag_idx)
        except ValueError:
            pass

    last_end = max(start_s, link.medium_free_at_s, job.arrival_time_s)
    for idx in sorted(missing):
        frame = frames[idx]

        def on_deliver_idx(frame_bytes: bytes, arr: float, frag_idx: int = idx) -> None:
            on_deliver(frame_bytes, arr, frag_idx)

        last_end = link.transmit(frame, last_end, "forward", on_deliver_idx)
        result.total_frames_tx += 1

    ack_bitmap_rx: int | None = None

    def on_ack(ack_bytes: bytes, _arr: float) -> None:
        nonlocal ack_bitmap_rx
        try:
            wf = WireFrame.unpack(ack_bytes)
            ack_bitmap_rx = struct.unpack("<I", wf.payload)[0]
        except ValueError:
            pass

    bitmap = _set_to_bitmap(received_fwd)
    ack_frame = build_ack_frame(
        job_state["seq"],
        total,
        bitmap,
        job.priority_int,
        0,
        pflags,
    )
    gap = link.prop_delay_s * float(arq_cfg.get("receiver_ack_gap_factor", 1.5))
    ack_start = last_end + gap
    last_end = link.transmit(ack_frame, ack_start, "return", on_ack)
    result.ack_frames_tx += 1

    if ack_bitmap_rx is not None:
        confirmed |= _bitmap_to_set(ack_bitmap_rx, total)
    job_state["confirmed"] = confirmed
    still_missing = set(range(total)) - confirmed
    job_state["missing"] = still_missing

    if not still_missing:
        pri = job.priority_int
        latency = last_end - job.arrival_time_s
        if latency <= deadline_s(job.detection.priority):
            result.delivered_within[pri] += 1
        else:
            result.delivered_late[pri] += 1
        result.latencies.append(latency)
        result.latencies_by_priority[pri].append(latency)
        if metrics is not None:
            metrics.record_delivery(pri, latency)
        result.delivered_bytes += len(job.payload)
        job_state["done"] = True
        job_state["timer_end"] = None
        return

    base_rto = (
        link.airtime_s(len(ack_frame))
        + link.turnaround_s
        + 2 * link.prop_delay_s
        + float(arq_cfg.get("rto_margin_s", 0.25))
    )
    attempt = job_state["attempt"]
    rto = min(float(arq_cfg.get("rto_cap_s", 30.0)), base_rto * (1.5 ** attempt))
    job_state["timer_end"] = max(link.medium_free_at_s, last_end) + rto
    job_state["done"] = False
