#!/usr/bin/env python3
"""Forbidden positive-claim wording audit (marker-block aware)."""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

PATTERNS = [
    r"USMTF[- ]conformant",
    r"MIL-STD-6040[- ]compliant",
    r"ADatP-3[- ]compliant",
    r"NCDF[- ](aligned|certified|compliant|conformant)",
    r"certified",
    r"TRL ?[5-9]",
    r"Link 16[- ](compatible|interoperable)",
    r"STANAG (4539|5066)[- ]compliant",
    r"field-tested",
    r"battle-proven",
    r"combat-ready",
    r"derived from F\.1487",
]

HITUAV_PUBLIC_DOMAIN = re.compile(r"public[- ]domain.*HIT-UAV|HIT-UAV.*public[- ]domain", re.I)

BEGIN = "<!-- NOT-CLAIMED:BEGIN -->"
END = "<!-- NOT-CLAIMED:END -->"


def strip_markers(text: str) -> str:
    out = []
    i = 0
    while i < len(text):
        start = text.find(BEGIN, i)
        if start == -1:
            out.append(text[i:])
            break
        out.append(text[i:start])
        end = text.find(END, start)
        if end == -1:
            break
        i = end + len(END)
    return "".join(out)


def audit_text(text: str, path: str) -> list[str]:
    hits = []
    for line_no, line in enumerate(text.splitlines(), 1):
        for pat in PATTERNS:
            if re.search(pat, line, re.I):
                hits.append(f"{path}:{line_no}: {pat}")
        if HITUAV_PUBLIC_DOMAIN.search(line):
            hits.append(f"{path}:{line_no}: public-domain+HIT-UAV")
    return hits


def audit_file(path: Path) -> list[str]:
    raw = path.read_text(encoding="utf-8", errors="replace")
    cleaned = strip_markers(raw)
    return audit_text(cleaned, str(path))


def main() -> int:
    targets = [ROOT / "README.md", ROOT / "results/SUMMARY.md", ROOT / "docs"]
    hits: list[str] = []
    for target in targets:
        if target.is_dir():
            for p in target.rglob("*"):
                if p.suffix in {".md", ".json"} and p.is_file():
                    hits.extend(audit_file(p))
        elif target.is_file():
            hits.extend(audit_file(target))
    if hits:
        print("\n".join(hits))
        return 1
    print("0 matches")
    return 0


if __name__ == "__main__":
    sys.exit(main())
