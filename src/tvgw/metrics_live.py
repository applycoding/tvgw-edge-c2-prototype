"""In-process metrics registry and stdlib HTTP exposition.

The text on ``/metrics`` follows the Prometheus text exposition format.
This module does not talk to a Prometheus server or any other collector.
"""

from __future__ import annotations

import math
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Mapping

LINK_STATES = ("busy", "down", "idle")
PRIORITIES = (0, 1, 2)


def _format_value(value: float) -> str:
    if isinstance(value, bool) or not math.isfinite(float(value)):
        raise ValueError("metric value must be a finite number")
    number = float(value)
    if number.is_integer():
        return str(int(number))
    return format(number, ".6f")


def _escape_label(value: str) -> str:
    return value.replace("\\", "\\\\").replace("\n", "\\n").replace('"', '\\"')


class LiveMetrics:
    """Cumulative snapshot for one laboratory scenario."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.queue_depth = 0
        self.queue_depth_max = 0
        self.latency_sum = {pri: 0.0 for pri in PRIORITIES}
        self.latency_count = {pri: 0 for pri in PRIORITIES}
        self.retries = 0
        self.failures = {pri: 0 for pri in PRIORITIES}
        self.validation_rejects = 0
        self.link_state = "idle"

    def observe(
        self,
        *,
        queue_depth: int,
        link_state: str,
        retries: int,
        failures: Mapping[int, int],
    ) -> None:
        if link_state not in LINK_STATES:
            raise ValueError(f"unknown link state: {link_state}")
        with self._lock:
            self.queue_depth = int(queue_depth)
            if self.queue_depth > self.queue_depth_max:
                self.queue_depth_max = self.queue_depth
            self.link_state = link_state
            self.retries = int(retries)
            self.failures = {pri: int(failures.get(pri, 0)) for pri in PRIORITIES}

    def record_delivery(self, priority: int, latency_s: float) -> None:
        if priority not in self.latency_sum:
            raise ValueError(f"unknown priority: {priority}")
        if not math.isfinite(float(latency_s)):
            raise ValueError("latency must be finite")
        with self._lock:
            self.latency_sum[priority] += float(latency_s)
            self.latency_count[priority] += 1

    def add_validation_rejects(self, count: int = 1) -> None:
        if count < 0:
            raise ValueError("validation reject count must be non-negative")
        with self._lock:
            self.validation_rejects += int(count)

    def render_prometheus(self) -> str:
        with self._lock:
            queue_depth = self.queue_depth
            queue_depth_max = self.queue_depth_max
            latency_sum = dict(self.latency_sum)
            latency_count = dict(self.latency_count)
            retries = self.retries
            failures = dict(self.failures)
            validation_rejects = self.validation_rejects
            link_state = self.link_state
        lines = [
            "# HELP tvgw_queue_depth Laboratory simulator gauge: gateway queue depth at the latest sample.",
            "# TYPE tvgw_queue_depth gauge",
            f"tvgw_queue_depth {_format_value(queue_depth)}",
            "# HELP tvgw_queue_depth_max Laboratory simulator gauge: maximum gateway queue depth in the run.",
            "# TYPE tvgw_queue_depth_max gauge",
            f"tvgw_queue_depth_max {_format_value(queue_depth_max)}",
            "# HELP tvgw_delivery_latency_seconds Laboratory simulator summary: delivery latency in seconds by priority.",
            "# TYPE tvgw_delivery_latency_seconds summary",
        ]
        for pri in PRIORITIES:
            label = _escape_label(str(pri))
            lines.append(
                f'tvgw_delivery_latency_seconds_sum{{priority="{label}"}} {_format_value(latency_sum[pri])}'
            )
            lines.append(
                f'tvgw_delivery_latency_seconds_count{{priority="{label}"}} {_format_value(latency_count[pri])}'
            )
        lines.extend(
            [
                "# HELP tvgw_retries_total Laboratory simulator counter: ARQ fragment retransmissions.",
                "# TYPE tvgw_retries_total counter",
                f"tvgw_retries_total {_format_value(retries)}",
                "# HELP tvgw_failures_total Laboratory simulator counter: messages that exhausted retries, by priority.",
                "# TYPE tvgw_failures_total counter",
            ]
        )
        for pri in PRIORITIES:
            label = _escape_label(str(pri))
            lines.append(f'tvgw_failures_total{{priority="{label}"}} {_format_value(failures[pri])}')
        lines.extend(
            [
                "# HELP tvgw_validation_rejects_total Laboratory simulator counter: profile validation rejects.",
                "# TYPE tvgw_validation_rejects_total counter",
                f"tvgw_validation_rejects_total {_format_value(validation_rejects)}",
                "# HELP tvgw_link_state Laboratory simulator gauge: 1 for the latest link state, 0 for the others.",
                "# TYPE tvgw_link_state gauge",
            ]
        )
        for state in LINK_STATES:
            flag = 1 if state == link_state else 0
            lines.append(f'tvgw_link_state{{state="{state}"}} {_format_value(flag)}')
        return "\n".join(lines) + "\n"


class _MetricsHandler(BaseHTTPRequestHandler):
    registry: LiveMetrics

    def do_GET(self) -> None:  # noqa: N802
        path = self.path.split("?", 1)[0]
        if path != "/metrics":
            body = b"not found\n"
            self._send(404, "text/plain; charset=utf-8", body)
            return
        body = self.registry.render_prometheus().encode("utf-8")
        self._send(200, "text/plain; version=0.0.4; charset=utf-8", body)

    def _send(self, status: int, content_type: str, body: bytes) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, format: str, *args: object) -> None:
        return


def make_metrics_server(registry: LiveMetrics, host: str = "127.0.0.1", port: int = 0) -> ThreadingHTTPServer:
    handler = type("BoundMetricsHandler", (_MetricsHandler,), {"registry": registry})
    return ThreadingHTTPServer((host, port), handler)


def start_metrics_server(
    registry: LiveMetrics,
    host: str = "127.0.0.1",
    port: int = 0,
) -> tuple[ThreadingHTTPServer, threading.Thread]:
    server = make_metrics_server(registry, host, port)
    thread = threading.Thread(target=server.serve_forever, name="tvgw-metrics", daemon=True)
    thread.start()
    return server, thread


def serve_metrics_forever(registry: LiveMetrics, host: str = "127.0.0.1", port: int = 0) -> None:
    server = make_metrics_server(registry, host, port)
    try:
        server.serve_forever()
    finally:
        server.server_close()
