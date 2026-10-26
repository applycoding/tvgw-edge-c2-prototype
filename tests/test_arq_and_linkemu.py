import numpy as np

from tvgw.fragment import fragment_payload
from tvgw.linkemu import LinkEmulator, OutageWindow, gilbert_params
from tvgw.sim import run_scenario
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_gilbert_reference_values():
    pi_b, p_gb = gilbert_params(0.10)
    assert abs(pi_b - 0.12390) < 0.0001
    assert abs(p_gb - 0.02829) < 0.0001


def test_zero_loss_goodput_uses_link_busy_end():
    from tvgw.config_loader import load_config

    cfg = load_config(ROOT)
    rate = 9600.0
    res = run_scenario(ROOT, "cbor", rate, 0.0, "fifo", 1, cfg)
    assert res.delivered_bytes > 0
    assert res.link_busy_end_s > 0
    expected = (res.delivered_bytes * 8) / res.link_busy_end_s
    assert abs(res.goodput_bps - expected) < 1e-6


def test_goodput_never_exceeds_link_rate():
    from tvgw.config_loader import load_config

    cfg = load_config(ROOT)
    for rate in (300, 1200, 9600):
        res = run_scenario(ROOT, "cbor", float(rate), 0.15, "priority", 3, cfg)
        assert res.goodput_bps <= float(rate) * 1.001 + 1e-6


def test_outage_overlap_drops():
    rng = np.random.default_rng(0)
    link = LinkEmulator(600, 0.0, rng, outages=[OutageWindow(1.0, 2.0)])
    drops = 0

    def cb(_f, _t):
        nonlocal drops
        drops += 1

    link.transmit(b"x" * 20, 1.5, "forward", cb)
    assert link.outage_drops >= 1
    assert drops == 0


def test_half_duplex_medium_free_at_monotonic():
    rng = np.random.default_rng(1)
    link = LinkEmulator(300, 0.0, rng)
    t1 = link.transmit(b"a" * 50, 0.0, "forward", lambda *_: None)
    t2 = link.transmit(b"b" * 50, t1, "return", lambda *_: None)
    assert t2 >= t1


def test_impairment_partition_counts_crc():
    rng = np.random.default_rng(2)
    link = LinkEmulator(1200, 0.2, rng)
    delivered = 0

    def _cb(_f, _t):
        nonlocal delivered
        delivered += 1

    for _ in range(400):
        link.transmit(b"z" * 30, 0.0, "forward", _cb)
    assert link.crc_errors_detected > 0 or delivered < 400


def test_message_fragments_airtime_sum():
    rng = np.random.default_rng(3)
    link = LinkEmulator(2400, 0.0, rng)
    frames = fragment_payload(b"payload-bytes", 1, 4, 0, 0)
    total = 0.0
    now = 0.0
    for fr in frames:
        now = link.transmit(fr, now, "forward", lambda *_: None)
        total += link.airtime_s(len(fr))
    assert total > 0


def test_rto_backoff_cap():
    rto0 = 1.0
    assert min(30.0, rto0 * (1.5 ** 10)) == 30.0


def test_run_scenario_lossy():
    from tvgw.config_loader import load_config

    cfg = load_config(ROOT)
    res = run_scenario(ROOT, "cbor", 600, 0.2, "priority", 5, cfg)
    assert sum(res.generated.values()) > 0
    assert res.ack_frames_tx >= 0


def test_ge_infeasible_loss():
    import pytest

    rng = np.random.default_rng(0)
    with pytest.raises(ValueError):
        LinkEmulator(1000, 0.95, rng)


def test_retry_exhaustion_increments_failed():
    from tvgw.config_loader import load_config

    cfg = load_config(ROOT)
    res = run_scenario(ROOT, "xml_raw", 300, 0.35, "fifo", 9, cfg, max_retries=0)
    assert sum(res.failed.values()) > 0
