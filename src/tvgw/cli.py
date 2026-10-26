"""tvgw CLI."""

from __future__ import annotations

import argparse
from pathlib import Path

from tvgw.config_loader import load_config
from tvgw.corpus import load_held_out
from tvgw.mapping.niem_mo import detection_to_niem_xml
from tvgw.mapping.text_report import detection_to_text_report
from tvgw.sim import run_scenario
from tvgw.validate import validate_combined


def main() -> None:
    parser = argparse.ArgumentParser(prog="tvgw")
    sub = parser.add_subparsers(dest="cmd", required=True)
    v = sub.add_parser("validate")
    v.add_argument("--limit", type=int, default=5)
    r = sub.add_parser("replay")
    r.add_argument("--rate-bps", type=float, default=600)
    r.add_argument("--loss", type=float, default=0.2)
    r.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    cfg = load_config(root)
    if args.cmd == "validate":
        held = load_held_out(root)
        ok = 0
        for d in held[: args.limit]:
            xml = detection_to_niem_xml(d)
            if validate_combined(xml, root).ok:
                ok += 1
            print(detection_to_text_report(d)[:120], "...")
        print(f"validated {ok}/{min(args.limit, len(held))}")
    elif args.cmd == "replay":
        res = run_scenario(root, "cbor", args.rate_bps, args.loss, "priority", args.seed, cfg)
        print(res)
