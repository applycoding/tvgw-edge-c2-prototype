"""tvgw CLI."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from typing import Literal, Never, NoReturn

from tvgw.config_loader import load_config
from tvgw.corpus import load_held_out
from tvgw.mapping.niem_mo import detection_to_niem_xml
from tvgw.mapping.text_report import detection_to_text_report
from tvgw.messages import CATALOG, translate, unsupported_language_text
from tvgw.metrics_live import LiveMetrics, make_metrics_server
from tvgw.sim import SimResult, generate_arrivals, run_scenario
from tvgw.validate import count_profile_rejects, validate_combined

CommandName = Literal["validate", "replay", "metrics"]


def _requested_lang(argv: list[str]) -> str:
    lang = "en"
    index = 0
    while index < len(argv):
        arg = argv[index]
        if arg == "--lang" and index + 1 < len(argv):
            lang = argv[index + 1]
            index += 2
            continue
        if arg.startswith("--lang="):
            lang = arg.split("=", 1)[1]
        index += 1
    if lang not in CATALOG:
        sys.stderr.write(unsupported_language_text(lang))
        raise SystemExit(2)
    return lang


def _fail(lang: str, key: str, **kwargs: str | int | float) -> NoReturn:
    sys.stderr.write(translate(lang, key, **kwargs) + "\n")
    raise SystemExit(2)


def _parse_int(lang: str, raw: str, name: str) -> int:
    try:
        return int(raw, 10)
    except ValueError:
        _fail(lang, "error.expected_int", name=name)


def _parse_float(lang: str, raw: str, name: str) -> float:
    try:
        return float(raw)
    except ValueError:
        _fail(lang, "error.expected_float", name=name)


def _parse_rate(lang: str, raw: str) -> float:
    rate = _parse_float(lang, raw, "rate-bps")
    if rate <= 0:
        _fail(lang, "error.rate_positive")
    return rate


def _parse_loss(lang: str, raw: str) -> float:
    loss = _parse_float(lang, raw, "loss")
    if loss < 0 or loss > 1:
        _fail(lang, "error.loss_range")
    return loss


def _parse_seed(lang: str, raw: str) -> int:
    seed = _parse_int(lang, raw, "seed")
    if seed < 0:
        _fail(lang, "error.seed_nonnegative")
    return seed


def _parse_limit(lang: str, raw: str) -> int:
    limit = _parse_int(lang, raw, "limit")
    if limit < 0:
        _fail(lang, "error.limit_nonnegative")
    return limit


def _parse_port(lang: str, raw: str) -> int:
    port = _parse_int(lang, raw, "port")
    if port < 0 or port > 65535:
        _fail(lang, "error.port")
    return port


def _parse_scheduling(lang: str, raw: str) -> str:
    if raw not in ("priority", "fifo"):
        _fail(lang, "error.scheduling")
    return raw


def _build_parser(lang: str) -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="tvgw", description=translate(lang, "cli.root.help"))
    sub = parser.add_subparsers(dest="cmd", required=True)

    validate = sub.add_parser(
        "validate",
        help=translate(lang, "cli.validate.help"),
        description=translate(lang, "cli.validate.help"),
    )
    validate.add_argument("--limit", default="5", help=translate(lang, "cli.validate.limit"))
    validate.add_argument("--lang", default="en", help=translate(lang, "cli.lang"))

    replay = sub.add_parser(
        "replay",
        help=translate(lang, "cli.replay.help"),
        description=translate(lang, "cli.replay.help"),
    )
    replay.add_argument("--rate-bps", default="600", help=translate(lang, "cli.replay.rate"))
    replay.add_argument("--loss", default="0.2", help=translate(lang, "cli.replay.loss"))
    replay.add_argument("--seed", default="42", help=translate(lang, "cli.replay.seed"))
    replay.add_argument("--scheduling", default="priority", help=translate(lang, "cli.replay.scheduling"))
    replay.add_argument("--lang", default="en", help=translate(lang, "cli.lang"))

    metrics = sub.add_parser("metrics", help=translate(lang, "cli.metrics.help"))
    metrics_sub = metrics.add_subparsers(dest="metrics_cmd", required=True)
    serve = metrics_sub.add_parser(
        "serve",
        help=translate(lang, "cli.metrics.serve.help"),
        description=translate(lang, "cli.metrics.serve.help"),
    )
    serve.add_argument("--host", default="127.0.0.1", help=translate(lang, "cli.metrics.host"))
    serve.add_argument("--port", default="0", help=translate(lang, "cli.metrics.port"))
    serve.add_argument("--rate-bps", default="600", help=translate(lang, "cli.replay.rate"))
    serve.add_argument("--loss", default="0.0", help=translate(lang, "cli.replay.loss"))
    serve.add_argument("--seed", default="42", help=translate(lang, "cli.replay.seed"))
    serve.add_argument("--scheduling", default="priority", help=translate(lang, "cli.metrics.scheduling"))
    serve.add_argument("--lang", default="en", help=translate(lang, "cli.lang"))
    return parser


def format_replay(lang: str, result: SimResult) -> str:
    lines = [
        translate(lang, "cli.replay.generated", p0=result.generated[0], p1=result.generated[1], p2=result.generated[2]),
        translate(
            lang,
            "cli.replay.delivered_within",
            p0=result.delivered_within[0],
            p1=result.delivered_within[1],
            p2=result.delivered_within[2],
        ),
        translate(
            lang,
            "cli.replay.delivered_late",
            p0=result.delivered_late[0],
            p1=result.delivered_late[1],
            p2=result.delivered_late[2],
        ),
        translate(lang, "cli.replay.failed", p0=result.failed[0], p1=result.failed[1], p2=result.failed[2]),
        translate(lang, "cli.replay.expired", p0=result.expired[0], p1=result.expired[1], p2=result.expired[2]),
        translate(lang, "cli.replay.retries", n=result.arq_retransmissions),
    ]
    return "\n".join(lines)


def run_replay_metrics(
    root: Path,
    cfg: dict,
    *,
    rate_bps: float,
    loss: float,
    seed: int,
    scheduling: str,
) -> tuple[SimResult, LiveMetrics]:
    """Run one scenario and publish its counters, including profile rejects."""
    registry = LiveMetrics()
    result = run_scenario(root, "cbor", rate_bps, loss, scheduling, seed, cfg, metrics=registry)
    arrivals = generate_arrivals(load_held_out(root), seed, cfg)
    registry.add_validation_rejects(count_profile_rejects([det for _, det in arrivals]))
    return result, registry


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _dispatch(cmd: CommandName, args: argparse.Namespace, lang: str, root: Path, cfg: dict) -> None:
    if cmd == "validate":
        limit = _parse_limit(lang, args.limit)
        held = load_held_out(root)
        ok = 0
        shown = held[:limit]
        for det in shown:
            xml = detection_to_niem_xml(det)
            outcome = validate_combined(xml, root)
            if outcome.ok:
                ok += 1
            else:
                print(translate(lang, "cli.validate.rejected", detection_id=det.detection_id, reason=outcome.message))
            print(detection_to_text_report(det, lang=lang)[:120], "...")
        print(translate(lang, "cli.validate.summary", ok=ok, total=len(shown)))
        return
    if cmd == "replay":
        rate = _parse_rate(lang, args.rate_bps)
        loss = _parse_loss(lang, args.loss)
        seed = _parse_seed(lang, args.seed)
        scheduling = _parse_scheduling(lang, args.scheduling)
        result, _registry = run_replay_metrics(
            root,
            cfg,
            rate_bps=rate,
            loss=loss,
            seed=seed,
            scheduling=scheduling,
        )
        print(format_replay(lang, result))
        return
    if cmd == "metrics":
        _serve_metrics(args, lang, root, cfg)
        return
    unexpected: Never = cmd
    raise AssertionError(unexpected)


def _serve_metrics(args: argparse.Namespace, lang: str, root: Path, cfg: dict) -> None:
    rate = _parse_rate(lang, args.rate_bps)
    loss = _parse_loss(lang, args.loss)
    seed = _parse_seed(lang, args.seed)
    scheduling = _parse_scheduling(lang, args.scheduling)
    port = _parse_port(lang, args.port)
    host = str(args.host).strip()
    if not host:
        _fail(lang, "error.host_empty")
    _result, registry = run_replay_metrics(
        root,
        cfg,
        rate_bps=rate,
        loss=loss,
        seed=seed,
        scheduling=scheduling,
    )
    server = make_metrics_server(registry, host, port)
    bound_host, bound_port = server.server_address
    print(translate(lang, "cli.metrics.listening", host=bound_host, port=bound_port), flush=True)
    serve_until_interrupt(server)


def serve_until_interrupt(server) -> None:
    """Serve until Ctrl-C, then close the listening socket without a traceback."""
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        return
    finally:
        server.server_close()


def main(argv: list[str] | None = None) -> None:
    if argv is None:
        argv = sys.argv[1:]
    lang = _requested_lang(argv)
    parser = _build_parser(lang)
    args = parser.parse_args(argv)
    root = _repo_root()
    cfg = load_config(root)
    cmd: CommandName = args.cmd
    _dispatch(cmd, args, lang, root, cfg)
