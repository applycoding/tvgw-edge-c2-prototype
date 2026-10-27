import json
import urllib.error
import urllib.request
from pathlib import Path

import pytest

from tests.prometheus_text import PrometheusTextError, parse_prometheus_text, sample_value
from tvgw.config_loader import load_config
from tvgw.metrics_live import LiveMetrics, start_metrics_server
from tvgw.sim import run_scenario

ROOT = Path(__file__).resolve().parents[1]


def _scrape(port: int, path: str) -> tuple[int, str, str]:
    last_error: Exception | None = None
    for _ in range(30):
        try:
            with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=2) as response:
                return response.status, response.headers.get("Content-Type", ""), response.read().decode("utf-8")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8")
            return exc.code, exc.headers.get("Content-Type", ""), body
        except urllib.error.URLError as exc:
            last_error = exc
    raise AssertionError(last_error)


def test_parser_rejects_malformed_exposition():
    with pytest.raises(PrometheusTextError):
        parse_prometheus_text("tvgw_queue_depth 1\n")
    with pytest.raises(PrometheusTextError):
        parse_prometheus_text("# TYPE tvgw_queue_depth notatype\ntvgw_queue_depth 1\n")
    with pytest.raises(PrometheusTextError):
        parse_prometheus_text("# TYPE tvgw_queue_depth gauge\ntvgw_queue_depth not_a_number\n")


def test_http_metrics_match_simulator_snapshot():
    cfg = json.loads(json.dumps(load_config(ROOT)))
    cfg["sim"]["background_count"] = 4
    cfg["sim"]["burst_count"] = 1
    cfg["sim"]["heartbeat_count"] = 1
    cfg["sim"]["arrival_window_s"] = 20.0
    cfg["sim"]["drain_horizon_s"] = 60.0
    registry = LiveMetrics()
    result = run_scenario(ROOT, "cbor", 9600, 0.0, "priority", 7, cfg, metrics=registry)
    registry.add_validation_rejects(2)
    server, thread = start_metrics_server(registry, "127.0.0.1", 0)
    port = server.server_address[1]
    try:
        status, content_type, body = _scrape(port, "/metrics")
        assert status == 200
        assert "text/plain" in content_type
        assert "version=0.0.4" in content_type
        families = parse_prometheus_text(body)
        assert sample_value(families, "tvgw_queue_depth") == registry.queue_depth
        assert sample_value(families, "tvgw_queue_depth_max") == registry.queue_depth_max
        assert sample_value(families, "tvgw_retries_total") == result.arq_retransmissions
        assert sample_value(families, "tvgw_validation_rejects_total") == 2
        for priority in (0, 1, 2):
            labels = {"priority": str(priority)}
            assert sample_value(families, "tvgw_failures_total", labels) == result.failed[priority]
            latencies = result.latencies_by_priority[priority]
            assert sample_value(families, "tvgw_delivery_latency_seconds_count", labels) == len(latencies)
            assert sample_value(families, "tvgw_delivery_latency_seconds_sum", labels) == pytest.approx(
                sum(latencies)
            )
        states = {
            state: sample_value(families, "tvgw_link_state", {"state": state}) for state in ("busy", "down", "idle")
        }
        assert sum(states.values()) == 1
        assert states[registry.link_state] == 1
        missing_status, _, missing_body = _scrape(port, "/other")
        assert missing_status == 404
        assert missing_body == "not found\n"
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=5)
