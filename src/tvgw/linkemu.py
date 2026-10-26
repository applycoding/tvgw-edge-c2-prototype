"""Half-duplex Gilbert-Elliott link emulator."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Callable, List

import numpy as np


@dataclass
class OutageWindow:
    start_s: float
    end_s: float


@dataclass
class LinkEmulator:
    rate_bps: float
    target_loss: float
    rng: np.random.Generator
    turnaround_s: float = 0.20
    prop_delay_s: float = 0.05
    jitter_s: float = 0.01
    preamble_bytes: int = 4
    medium_free_at_s: float = 0.0
    last_direction: str | None = None
    outages: List[OutageWindow] = field(default_factory=list)
    outage_drops: int = 0
    crc_errors_detected: int = 0
    state: str = "GOOD"
    e_good: float = 0.001
    e_bad: float = 0.80
    p_bg: float = 0.20
    p_gb: float = 0.0
    pi_b: float = 0.0

    def __post_init__(self) -> None:
        self._configure_ge()

    def _configure_ge(self) -> None:
        if self.target_loss == 0.0:
            self.e_good = 0.0
            self.e_bad = 0.0
            self.p_gb = 0.0
            self.pi_b = 0.0
            self.state = "GOOD"
            return
        if not (self.e_good <= self.target_loss <= self.e_bad):
            raise ValueError("infeasible target loss")
        self.pi_b = (self.target_loss - self.e_good) / (self.e_bad - self.e_good)
        self.p_gb = (self.pi_b * self.p_bg) / (1.0 - self.pi_b)
        self.state = "BAD" if self.rng.random() < self.pi_b else "GOOD"

    def _step_markov(self) -> None:
        if self.target_loss == 0.0:
            return
        if self.state == "GOOD":
            if self.rng.random() < self.p_gb:
                self.state = "BAD"
        else:
            if self.rng.random() < self.p_bg:
                self.state = "GOOD"

    def airtime_s(self, wire_bytes: int) -> float:
        return 8.0 * (wire_bytes + self.preamble_bytes) / self.rate_bps

    def transmit(
        self,
        frame: bytes,
        now_s: float,
        direction: str,
        on_deliver: Callable[[bytes, float], None],
    ) -> float:
        self._step_markov()
        dir_changed = self.last_direction is not None and self.last_direction != direction
        tx_start = max(now_s, self.medium_free_at_s + (self.turnaround_s if dir_changed else 0.0))
        airtime = self.airtime_s(len(frame))
        tx_end = tx_start + airtime
        self.medium_free_at_s = tx_end
        self.last_direction = direction
        arrival = tx_end + max(0.001, self.prop_delay_s + self.rng.uniform(-self.jitter_s, self.jitter_s))

        for win in self.outages:
            if tx_start < win.end_s and arrival > win.start_s:
                self.outage_drops += 1
                return tx_end

        impaired_p = self.e_good if self.state == "GOOD" else self.e_bad
        delivered = frame
        if self.rng.random() < impaired_p:
            if self.rng.random() < 0.80:
                return tx_end
            delivered = _flip_bits(frame, self.rng)
            try:
                from tvgw.fragment import WireFrame

                WireFrame.unpack(delivered)
            except ValueError:
                self.crc_errors_detected += 1
                return tx_end
            self.crc_errors_detected += 1
            return tx_end

        on_deliver(delivered, arrival)
        return tx_end


def _flip_bits(data: bytes, rng: np.random.Generator) -> bytes:
    if not data:
        return data
    n = int(rng.integers(1, 4))
    arr = bytearray(data)
    for _ in range(n):
        idx = int(rng.integers(0, len(arr)))
        bit = 1 << int(rng.integers(0, 8))
        arr[idx] ^= bit
    return bytes(arr)


def gilbert_params(target_loss: float) -> tuple[float, float]:
    e_g, e_b, p_bg = 0.001, 0.80, 0.20
    if target_loss == 0:
        return 0.0, 0.0
    pi_b = (target_loss - e_g) / (e_b - e_g)
    p_gb = (pi_b * p_bg) / (1.0 - pi_b)
    return pi_b, p_gb
