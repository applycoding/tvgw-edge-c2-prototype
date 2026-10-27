"""Strict Prometheus text-exposition parser used by the metrics tests.

Accepts the 0.0.4 text format subset: HELP, TYPE, and samples with labels.
Exemplars are rejected. An optional numeric timestamp is accepted.
"""

from __future__ import annotations

import math
import re
from dataclasses import dataclass, field

NAME_RE = re.compile(r"[a-zA-Z_:][a-zA-Z0-9_:]*")
LABEL_RE = re.compile(r"[a-zA-Z_][a-zA-Z0-9_]*")
VALUE_RE = re.compile(r"[-+]?(?:Inf|NaN|(?:\d+\.\d*|\.\d+|\d+)(?:[eE][-+]?\d+)?)")
TYPES = {"counter", "gauge", "histogram", "summary", "untyped"}


@dataclass
class Sample:
    name: str
    labels: tuple[tuple[str, str], ...]
    value: float


@dataclass
class Family:
    name: str
    help_text: str | None = None
    metric_type: str | None = None
    samples: list[Sample] = field(default_factory=list)


class PrometheusTextError(ValueError):
    pass


def _parse_value(token: str) -> float:
    if token in ("NaN", "+NaN", "-NaN"):
        return float("nan")
    if token in ("+Inf", "Inf"):
        return float("inf")
    if token == "-Inf":
        return float("-inf")
    return float(token)


def _parse_labels(line: str, index: int, line_no: int) -> tuple[tuple[tuple[str, str], ...], int]:
    if index >= len(line) or line[index] != "{":
        return (), index
    index += 1
    labels: list[tuple[str, str]] = []
    seen: set[str] = set()
    if index < len(line) and line[index] == "}":
        return (), index + 1
    while True:
        match = LABEL_RE.match(line, index)
        if match is None:
            raise PrometheusTextError(f"line {line_no}: label name")
        label_name = match.group(0)
        if label_name in seen:
            raise PrometheusTextError(f"line {line_no}: duplicate label {label_name}")
        seen.add(label_name)
        index = match.end()
        if index >= len(line) or line[index] != "=":
            raise PrometheusTextError(f"line {line_no}: expected =")
        index += 1
        if index >= len(line) or line[index] != '"':
            raise PrometheusTextError(f"line {line_no}: expected quoted label")
        index += 1
        chars: list[str] = []
        closed = False
        while index < len(line):
            char = line[index]
            if char == "\\":
                if index + 1 >= len(line):
                    raise PrometheusTextError(f"line {line_no}: bad escape")
                nxt = line[index + 1]
                if nxt == "n":
                    chars.append("\n")
                elif nxt in {'\\', '"'}:
                    chars.append(nxt)
                else:
                    raise PrometheusTextError(f"line {line_no}: bad escape")
                index += 2
                continue
            if char == '"':
                index += 1
                closed = True
                break
            if char == "\n":
                raise PrometheusTextError(f"line {line_no}: raw newline in label")
            chars.append(char)
            index += 1
        if not closed:
            raise PrometheusTextError(f"line {line_no}: unclosed label")
        labels.append((label_name, "".join(chars)))
        if index < len(line) and line[index] == ",":
            index += 1
            continue
        if index < len(line) and line[index] == "}":
            return tuple(labels), index + 1
        raise PrometheusTextError(f"line {line_no}: expected label separator")


def _parse_sample(line: str, line_no: int) -> Sample:
    match = NAME_RE.match(line)
    if match is None:
        raise PrometheusTextError(f"line {line_no}: metric name")
    name = match.group(0)
    index = match.end()
    labels, index = _parse_labels(line, index, line_no)
    if index < len(line) and line[index] not in " \t":
        raise PrometheusTextError(f"line {line_no}: expected whitespace before value")
    rest = line[index:].strip()
    if not rest:
        raise PrometheusTextError(f"line {line_no}: missing value")
    if " #" in rest or rest.startswith("#"):
        raise PrometheusTextError(f"line {line_no}: exemplars are not accepted")
    parts = rest.split()
    value_match = VALUE_RE.fullmatch(parts[0])
    if value_match is None:
        raise PrometheusTextError(f"line {line_no}: bad value")
    if len(parts) > 2:
        raise PrometheusTextError(f"line {line_no}: trailing junk")
    if len(parts) == 2 and VALUE_RE.fullmatch(parts[1]) is None:
        raise PrometheusTextError(f"line {line_no}: bad timestamp")
    return Sample(name, labels, _parse_value(parts[0]))


def parse_prometheus_text(text: str) -> dict[str, Family]:
    if text and not text.endswith("\n"):
        raise PrometheusTextError("exposition must end with a newline")
    families: dict[str, Family] = {}
    current: str | None = None
    for line_no, line in enumerate(text.splitlines(), 1):
        if line == "":
            continue
        if line.startswith("#"):
            parts = line.split(None, 3)
            if len(parts) >= 2 and parts[1] in {"HELP", "TYPE"}:
                if len(parts) < 3 or NAME_RE.fullmatch(parts[2]) is None:
                    raise PrometheusTextError(f"line {line_no}: bad {parts[1]} name")
                name = parts[2]
                family = families.get(name)
                if family is None:
                    if current is not None and families[current].metric_type is None:
                        raise PrometheusTextError(f"line {line_no}: {current} missing TYPE")
                    family = Family(name)
                    families[name] = family
                    current = name
                if parts[1] == "HELP":
                    if family.help_text is not None or family.metric_type is not None or family.samples:
                        raise PrometheusTextError(f"line {line_no}: HELP out of order")
                    family.help_text = parts[3] if len(parts) > 3 else ""
                else:
                    if family.metric_type is not None or family.samples:
                        raise PrometheusTextError(f"line {line_no}: TYPE out of order")
                    if len(parts) != 4 or parts[3] not in TYPES:
                        raise PrometheusTextError(f"line {line_no}: bad TYPE")
                    family.metric_type = parts[3]
                continue
            continue
        if current is None or families[current].metric_type is None:
            raise PrometheusTextError(f"line {line_no}: sample before TYPE")
        sample = _parse_sample(line, line_no)
        family_name = families[current].name
        if sample.name != family_name and not sample.name.startswith(family_name + "_"):
            raise PrometheusTextError(f"line {line_no}: sample {sample.name} outside {family_name}")
        families[current].samples.append(sample)
    for family in families.values():
        if family.metric_type is None:
            raise PrometheusTextError(f"{family.name}: missing TYPE")
        if not family.samples:
            raise PrometheusTextError(f"{family.name}: missing samples")
    return families


def sample_value(families: dict[str, Family], name: str, labels: dict[str, str] | None = None) -> float:
    wanted = tuple(sorted((labels or {}).items()))
    for family in families.values():
        for sample in family.samples:
            if sample.name == name and tuple(sorted(sample.labels)) == wanted:
                if math.isnan(sample.value):
                    raise PrometheusTextError(f"{name} is NaN")
                return sample.value
    raise KeyError(name)
