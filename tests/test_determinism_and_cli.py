import gzip
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _sha_decompressed_m3(path: Path) -> str:
    raw = gzip.decompress(path.read_bytes())
    return hashlib.sha256(raw).hexdigest()


def test_benchmark_m1_determinism(tmp_path):
    from scripts.run_all_benchmarks import run_m1

    out = tmp_path / "results"
    run_m1(ROOT, out)
    h1 = _sha(out / "m1_validation_summary.json")
    run_m1(ROOT, out)
    h2 = _sha(out / "m1_validation_summary.json")
    assert h1 == h2


def test_m3_ci_sweep_determinism(tmp_path):
    """SC-9: identical master seed -> identical decompressed M3 CSV content."""
    run1 = tmp_path / "run1"
    run2 = tmp_path / "run2"
    for out_dir in (run1, run2):
        subprocess.run(
            [
                PY,
                str(ROOT / "scripts/run_all_benchmarks.py"),
                "--mode",
                "ci",
                "--master-seed",
                "424242",
                "--results-dir",
                str(out_dir),
            ],
            check=True,
            cwd=ROOT,
        )
    h1 = _sha_decompressed_m3(run1 / "m3_delivery_sweep.csv.gz")
    h2 = _sha_decompressed_m3(run2 / "m3_delivery_sweep.csv.gz")
    assert h1 == h2 and h1 != ""


def test_cli_validate():
    out = subprocess.run(
        [PY, "-c", "import sys; from tvgw.cli import main; sys.argv=['tvgw','validate','--limit','1']; raise SystemExit(main())"],
        cwd=ROOT,
        capture_output=True,
        text=True,
    )
    assert out.returncode == 0


def test_audit_script(tmp_path):
    pos = tmp_path / "audit_positive.md"
    pos.write_text("This claims USMTF conformant mapping\n", encoding="utf-8")
    neg = tmp_path / "audit_negative.md"
    neg.write_text(
        "<!-- NOT-CLAIMED:BEGIN -->\nUSMTF conformant\n<!-- NOT-CLAIMED:END -->\n",
        encoding="utf-8",
    )
    sys.path.insert(0, str(ROOT))
    from scripts.audit_wording import audit_file

    assert audit_file(pos)
    assert not audit_file(neg)


def test_prometheus_file_finite():
    prom = ROOT / "results/metrics.prom"
    assert prom.is_file()
    text = prom.read_text()
    assert "_sum" in text and "_count" in text


def test_run_metadata_written():
    meta = ROOT / "results/run_metadata.json"
    assert meta.is_file()
    data = json.loads(meta.read_text())
    assert "wall_clock_s" in data
    assert "source_code_content_sha256" in data
    assert "git_commit" not in data
    assert "git_tree" not in data


def test_distinct_scenario_seed_changes_sim():
    from tvgw.config_loader import load_config
    from tvgw.sim import run_scenario

    cfg = load_config(ROOT)
    a = run_scenario(ROOT, "cbor", 600, 0.1, "priority", 1, cfg)
    b = run_scenario(ROOT, "cbor", 600, 0.1, "priority", 2, cfg)
    assert a.generated != b.generated or a.delivered_within != b.delivered_within
