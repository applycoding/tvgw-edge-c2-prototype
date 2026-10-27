import json
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def test_train_ids_file_is_firms_records():
    path = ROOT / "data" / "sample" / "firms_train_ids_500.json"
    assert path.is_file()
    assert not (ROOT / "data" / "sample" / "hituav_train_Ids_500.json").exists()
    ids = json.loads(path.read_text(encoding="utf-8"))
    assert len(ids) == 500
    assert all(item.startswith("FIRMS_") for item in ids)
    readme = (ROOT / "data" / "README.md").read_text(encoding="utf-8")
    assert "firms_train_ids_500.json" in readme
    assert "751beab1cbdfea7146a903c722d101385669b7cf4f1f6298637ae85446505c7a" in readme


def test_old_train_id_filename_is_only_historical():
    tracked = subprocess.run(
        ["git", "grep", "-l", "hituav_train_Ids_500", "--", ":!tests"],
        cwd=ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    if tracked.returncode == 1:
        return
    assert tracked.returncode == 0
    files = {line.strip() for line in tracked.stdout.splitlines() if line.strip()}
    assert files == {"data/README.md"}
