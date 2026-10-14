"""The downloadable bundles.

Two properties carry the weight here. **Reproducibility**: the same tree must
produce the same bytes, or "does my download match yours" has no answer and CI
cannot check the build. **Drop-in-ness**: what comes out of the unzip has to be
something `--items` accepts, or the download is only a souvenir.
"""
from __future__ import annotations

import hashlib
import json
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb.schema import load_items, validate_item  # noqa: E402

TOOL = ROOT / "tools" / "build_bundle.py"


def build(out: Path, *extra: str) -> subprocess.CompletedProcess:
    cmd = [sys.executable, str(TOOL), "--items", "items/bench10",
           "--workspace", "--out", str(out), *extra]
    proc = subprocess.run(cmd, capture_output=True, text=True, cwd=str(ROOT))
    assert proc.returncode == 0, proc.stderr
    return proc


@pytest.fixture(scope="module")
def download(tmp_path_factory) -> Path:
    out = tmp_path_factory.mktemp("dl")
    build(out)
    return out


def digest(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def test_default_formats_are_all_present(download: Path) -> None:
    assert {p.name for p in download.iterdir()} == {
        "acnlb-bench10.zip",
        "acnlb-bench10.bundle.json",
        "acnlb-workspace.zip",
        "manifest.json",
        "HOWTO.txt",
        "SHA256SUMS",
    }


def test_byte_reproducible(tmp_path: Path) -> None:
    """A rebuild that changed nothing must produce identical bytes.

    `zipfile` stamps members with the current time unless told otherwise, so this
    fails the moment somebody drops the explicit ZipInfo — which is exactly the
    regression worth catching, because the symptom is a new hash on every deploy
    and no other visible difference.
    """
    a = tmp_path / "a"
    b = tmp_path / "b"
    build(a)
    build(b)

    for name in sorted(p.name for p in a.iterdir()):
        assert digest(a / name) == digest(b / name), f"{name} differs between runs"


def test_manifest_checksums_match_the_files(download: Path) -> None:
    manifest = json.loads((download / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == ""
    by_name = {b["name"]: b for b in manifest["bundles"]}
    assert set(by_name) == {"bench10", "workspace"}

    bench = by_name["bench10"]
    assert bench["count"] == 10
    assert bench["total_points"] == 115.0
    for artifact in bench["artifacts"]:
        path = download / artifact["path"]
        assert path.is_file()
        assert path.stat().st_size == artifact["bytes"]
        assert digest(path) == artifact["sha256"]


def test_sha256sums_verifies(download: Path) -> None:
    for line in (download / "SHA256SUMS").read_text(encoding="utf-8").splitlines():
        want, name = line.split("  ")
        assert digest(download / name) == want, name


def test_items_zip_unpacks_into_a_valid_item_set(download: Path, tmp_path: Path) -> None:
    with zipfile.ZipFile(download / "acnlb-bench10.zip") as zf:
        assert zf.testzip() is None
        assert all(n.startswith("bench10/") for n in zf.namelist())
        zf.extractall(tmp_path)

    root = tmp_path / "bench10"
    items = load_items(root)
    assert [i.id for i in items] == [
        "core-lit-0003", "core-lit-0004", "core-lit-0005", "core-tx-0001", "core-tx-0002",
        "ret-0009", "ret-0010", "wf-0006", "wf-0007", "wf-0008",
    ]
    for item in items:
        assert validate_item(item, root) == []


def test_bundle_json_is_self_contained(download: Path) -> None:
    doc = json.loads((download / "acnlb-bench10.bundle.json").read_text(encoding="utf-8"))
    assert doc["kind"] == "items"
    assert doc["source"] == "items/bench10"
    assert len(doc["items"]) == 10
    for item in doc["items"]:
        assert "_rubric_text" in item and "## " in item["_rubric_text"]
        assert "_gold_text" in item
        assert item["max_positive_points"] > 0
        # Underscore keys are the bundler's; the schema owns everything else, so
        # an item that came out of the bundle must still load.
        from acnlb.schema import Item

        stripped = {k: v for k, v in item.items() if not k.startswith("_")}
        assert Item.from_dict(stripped).id == item["id"]


def test_workspace_zip_excludes_what_must_not_ship(download: Path) -> None:
    """`local/` never leaves the machine, and the rest is build noise."""
    with zipfile.ZipFile(download / "acnlb-workspace.zip") as zf:
        names = zf.namelist()

    assert "acnlb/acnlb/cli.py" in names
    assert "acnlb/items/bench10/core-tx-0001.json" in names
    assert "acnlb/tools/build_bundle.py" in names
    for forbidden in ("local/", "runs/", ".git/", ".venv/", "_site/", "site/download/", "AGENTS.md"):
        assert not any(n.startswith("acnlb/" + forbidden) for n in names), forbidden
    assert not any("__pycache__" in n for n in names)


def test_workspace_zip_is_runnable(tmp_path: Path, download: Path) -> None:
    """No clone, no git: unpack and the CLI answers."""
    with zipfile.ZipFile(download / "acnlb-workspace.zip") as zf:
        zf.extractall(tmp_path)
    repo = tmp_path / "acnlb"
    assert (repo / "acnlb" / "cli.py").is_file()

    proc = subprocess.run(
        [sys.executable, "-m", "acnlb", "validate", "--items", "items/bench10"],
        capture_output=True, text=True, cwd=str(repo),
    )
    assert proc.returncode == 0, proc.stdout + proc.stderr
    assert "OK" in proc.stdout


def test_formats_can_be_narrowed(tmp_path: Path) -> None:
    """A caller that wants only a zip must not be handed the rest."""
    build(tmp_path, "--formats", "zip")
    assert {p.name for p in tmp_path.iterdir()} == {"acnlb-bench10.zip", "acnlb-workspace.zip"}

    build(tmp_path / "b", "--formats", "manifest,sums,howto")
    assert {p.name for p in (tmp_path / "b").iterdir()} == {
        "manifest.json", "HOWTO.txt", "SHA256SUMS",
    }

    build(tmp_path / "c", "--formats", "howto")
    assert {p.name for p in (tmp_path / "c").iterdir()} == {"HOWTO.txt"}


def test_name_and_commit_are_recorded(tmp_path: Path) -> None:
    """--name is what the site links to, so it must reach the artifact names."""
    build(tmp_path, "--name", "trial", "--commit", "deadbeefcafe", "--formats", "zip,manifest")
    assert (tmp_path / "acnlb-trial.zip").is_file()
    assert not (tmp_path / "acnlb-bench10.zip").exists()

    manifest = json.loads((tmp_path / "manifest.json").read_text(encoding="utf-8"))
    assert manifest["commit"] == "deadbeefcafe"
    assert manifest["bundles"][0]["name"] == "trial"
    assert manifest["bundles"][0]["source"] == "items/bench10"


def test_extra_excludes_are_honoured(tmp_path: Path) -> None:
    build(tmp_path, "--formats", "zip", "--exclude", "notebooks")
    with zipfile.ZipFile(tmp_path / "acnlb-workspace.zip") as zf:
        assert not any(n.startswith("acnlb/notebooks") for n in zf.namelist())
