import hashlib
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def _sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def test_source_code_content_sha256_matches_run_metadata():
    import json

    from scripts.run_all_benchmarks import source_code_content_sha256

    meta = json.loads((ROOT / "results/run_metadata.json").read_text(encoding="utf-8"))
    stored = meta.get("source_code_content_sha256")
    assert stored
    assert source_code_content_sha256(ROOT) == stored


def test_held_out_hash_readme_matches_summary_and_corpus():
    from scripts.run_all_benchmarks import held_out_hash_from_data_readme

    readme_hash = held_out_hash_from_data_readme(ROOT)
    summary = (ROOT / "results/SUMMARY.md").read_text(encoding="utf-8")
    assert readme_hash in summary
    corp = ROOT / "data/corpus/held_out_5000.jsonl"
    if corp.is_file():
        assert _sha256_file(corp) == readme_hash
