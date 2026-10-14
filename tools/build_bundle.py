"""Build the downloadable bundles served from the site root.

The front page is served from `_site/`, which the deploy workflow assembles out
of `site/` and `results/` — `items/` is not in it, and never was. So "give me
this item set" used to mean "go to GitHub and find the tree". This tool writes
what a colleague actually wants into `_site/download/`: the item set as a zip you
can unpack straight into `--items`, the whole workspace as a zip you can run
without cloning, and a checksum file to confirm you got what the site published.

Everything is deterministic. The zip carries a fixed DOS timestamp, entries are
walked in sorted order, and the manifest records no wall-clock time — so the
same tree always produces the same bytes. That is what lets CI assert it, and
what lets a reader verify a download against the manifest.

Run:  python tools/build_bundle.py --out _site/download
      python tools/build_bundle.py --items items/bench10 --workspace --out _site/download
      python tools/build_bundle.py --items items/real --name real --out /tmp/dl
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # tools/ is not a package; run as a script
    sys.path.insert(0, str(ROOT))

from acnlb import SCHEMA_VERSION  # noqa: E402

DEFAULT_ITEMS = "items/bench10"
DEFAULT_OUT = "site/download"
FORMATS = ("zip", "bundle", "manifest", "sums", "howto")

# 1980-01-01T00:00:00Z — the earliest time the zip format can express, and a
# constant, so a rebuild that changed nothing produces the same bytes.
FIXED_DOS_TIME = (1980, 1, 1, 0, 0, 0)

# What a workspace bundle must never contain. `local/` is the one that matters
# (see the repo's red lines); the rest is build product and editor junk that would
# only make the download bigger and the diff noisier.
#
# A bare name matches that path component anywhere, not just at the root: a
# `__pycache__` under `tools/` and a `runs/` under `items/` are the same mistake
# as the root-level ones, and the first version of this matched neither, so a
# stale bytecode directory shipped inside every download.
WORKSPACE_EXCLUDES = (
    ".git",
    ".venv",
    "venv",
    "runs",
    "local",
    "AGENTS.md",
    ".workbuddy",
    ".pytest_cache",
    "__pycache__",
    ".DS_Store",
    "site/download",
    "_site",
    "build",
    "dist",
)


# ---------- deterministic archive ----------


def write_zip(entries: list[tuple[str, bytes]], *, dos_time=FIXED_DOS_TIME) -> bytes:
    """Zip `(arcname, data)` pairs, in the order given, reproducibly.

    `zipfile` stamps each member with the current time unless told otherwise, so
    a naive archive differs on every run. Passing an explicit ZipInfo pins the
    timestamp, the permission bits and the creation system in one place.
    """
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as zf:
        for arcname, data in entries:
            info = zipfile.ZipInfo(arcname, date_time=dos_time)
            info.create_system = 3  # unix, so external_attr is read as a mode
            is_dir = arcname.endswith("/")
            info.external_attr = (0o40755 if is_dir else 0o100644) << 16
            info.compress_type = zipfile.ZIP_STORED if is_dir else zipfile.ZIP_DEFLATED
            zf.writestr(info, data)
    return buf.getvalue()


def collect_dir(root: Path, prefix: str, *, excludes: tuple[str, ...] = ()) -> list[tuple[str, bytes]]:
    """Walk `root` in sorted order into `(arcname, data)` pairs under `prefix`.

    Directories get their own entries only when nothing under them survives the
    excludes. Zip readers create a directory from the paths of the files in it,
    so an entry for a populated directory is dead weight — but an empty one would
    be lost without it.
    """
    def excluded(rel: str) -> bool:
        parts = rel.split("/")
        for entry in excludes:
            if "/" in entry:
                if rel == entry or rel.startswith(entry + "/"):
                    return True
            elif entry in parts:
                return True
        return False

    kept = sorted(
        (p for p in root.rglob("*") if not excluded(p.relative_to(root).as_posix())),
        key=lambda p: p.relative_to(root).as_posix(),
    )
    has_file_under = {p for p in kept if p.is_file()}

    entries: list[tuple[str, bytes]] = []
    for path in kept:
        rel = path.relative_to(root).as_posix()
        if path.is_dir():
            if any(f.is_relative_to(path) for f in has_file_under):
                continue
            entries.append((prefix + rel + "/", b""))
            continue
        entries.append((prefix + rel, path.read_bytes()))
    return entries


def sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _file_facts(entries: list[tuple[str, bytes]], prefix: str) -> list[dict]:
    return [
        {"path": arc[len(prefix):], "bytes": len(data), "sha256": sha256(data)}
        for arc, data in entries
        if not arc.endswith("/")
    ]


# ---------- the two bundles ----------


def items_bundle(items_dir: Path, *, make_bundle: bool) -> dict:
    """The item set: a drop-in zip plus a single-file JSON for everything else."""
    entries = collect_dir(items_dir, items_dir.name + "/")
    bundle_doc = None
    if make_bundle:
        bundle_doc = build_bundle_json(items_dir, entries)
    return {
        "name": items_dir.name,
        "kind": "items",
        "source": rel(items_dir),
        "prefix": items_dir.name + "/",
        "entries": entries,
        "bundle_doc": bundle_doc,
        "summary": summarize_items(items_dir),
    }


def summarize_items(items_dir: Path) -> dict:
    items, total = [], 0.0
    for path in sorted(items_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        items.append(d.get("id") or path.stem)
        total += float(d.get("max_positive_points") or 0)
    return {"count": len(items), "total_points": total, "ids": items}


def build_bundle_json(items_dir: Path, entries: list[tuple[str, bytes]]) -> dict:
    """One JSON with every item inlined, for readers that will not unpack a zip.

    Rubric and gold text are attached under keys that start with an underscore —
    the schema owns everything else, and `Item.from_dict` has no `_` keys to
    collide with.
    """
    prefix = items_dir.name + "/"
    blobs = {arc[len(prefix):]: data for arc, data in entries if not arc.endswith("/")}
    items = []
    for path in sorted(items_dir.glob("*.json")):
        if path.name.startswith("_"):
            continue
        item = json.loads(path.read_text(encoding="utf-8"))
        rubric_rel = item.get("rubric")
        gold_rel = item.get("gold_answer")
        if rubric_rel and rubric_rel in blobs:
            item["_rubric_text"] = blobs[rubric_rel].decode("utf-8")
        if gold_rel and gold_rel in blobs:
            item["_gold_text"] = blobs[gold_rel].decode("utf-8")
        docs = {}
        for doc in item.get("documents") or []:
            key = doc["path"] if isinstance(doc, dict) else doc
            if key in blobs:
                try:
                    docs[key] = blobs[key].decode("utf-8")
                except UnicodeDecodeError:
                    pass  # binary attachment: it is in the zip, not in the JSON
        if docs:
            item["_documents"] = docs
        items.append(item)
    return {
        "kind": "items",
        "schema_version": SCHEMA_VERSION,
        "source": rel(items_dir),
        "items": items,
    }


def workspace_bundle(*, excludes: tuple[str, ...]) -> dict:
    """The whole harness, so a download runs without a clone and without git."""
    entries = collect_dir(ROOT, "acnlb/", excludes=excludes)
    return {
        "name": "workspace",
        "kind": "workspace",
        "source": ".",
        "prefix": "acnlb/",
        "entries": entries,
        "bundle_doc": None,
        "summary": summarize_items(ROOT / "items" / "bench10")
        if (ROOT / "items" / "bench10").is_dir()
        else {"count": 0, "total_points": 0.0, "ids": []},
    }


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


# ---------- output ----------


def howto(manifest_bundles: list[dict], commit: str) -> str:
    """Plain-text README next to the artifacts, generated from what was built."""
    lines = [
        "acnlb — downloadable item sets",
        "",
        "Files:",
    ]
    for b in manifest_bundles:
        for a in b["artifacts"]:
            label = "the workspace, unpacked as-is" if b["kind"] == "workspace" else "this item set"
            lines.append(f"  {a['path']:<32} {a['bytes']:>9} bytes  {label}")
    lines += [
        "  manifest.json                     every packed file, with size and sha256",
        "  SHA256SUMS                        verify with:  shasum -a 256 -c SHA256SUMS",
        "",
        "Run the harness on an item set:",
        "  python -m acnlb validate --items items/bench10",
        "  python -m acnlb run --items items/bench10 --model models.example.yaml --judge manual",
        "",
        "The workspace zip contains the harness, the item sets and the site, so it",
        "needs no clone. It excludes local/, runs/ and version-control data — a",
        "download is a snapshot, not a checkout.",
    ]
    if commit:
        lines += ["", f"Built from commit {commit}."]
    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", default=DEFAULT_ITEMS, help="item directory to publish")
    ap.add_argument("--name", default=None, help="bundle name (default: the directory name)")
    ap.add_argument("--workspace", action="store_true",
                    help="also publish the whole harness, so no clone is needed")
    ap.add_argument("--out", default=DEFAULT_OUT, help="output directory")
    ap.add_argument("--formats", default=",".join(FORMATS),
                    help=f"any of: {', '.join(FORMATS)}")
    ap.add_argument("--exclude", action="append", default=[],
                    help="extra path to drop from the workspace bundle (repeatable)")
    ap.add_argument("--commit", default="", help="commit sha to record in the manifest")
    args = ap.parse_args()

    formats = {f.strip() for f in args.formats.split(",") if f.strip()}
    unknown = formats - set(FORMATS)
    if unknown:
        print(f"error: unknown format(s) {sorted(unknown)}; known: {list(FORMATS)}", file=sys.stderr)
        return 2

    items_dir = (ROOT / args.items).resolve()
    if not items_dir.is_dir():
        print(f"error: {items_dir} is not a directory", file=sys.stderr)
        return 1
    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    name = args.name or items_dir.name
    bundles = [items_bundle(items_dir, make_bundle="bundle" in formats)]
    bundles[0]["name"] = name
    if args.workspace:
        excludes = tuple(WORKSPACE_EXCLUDES) + tuple(args.exclude)
        bundles.append(workspace_bundle(excludes=excludes))

    written: list[Path] = []

    def emit(p: Path, data: bytes) -> None:
        p.write_bytes(data)
        written.append(p)

    manifest_bundles = []
    for b in bundles:
        artifacts = []
        if "zip" in formats:
            zpath = out / f"acnlb-{b['name']}.zip"
            data = write_zip(b["entries"])
            emit(zpath, data)
            artifacts.append({"path": zpath.name, "bytes": len(data), "sha256": sha256(data)})
        if "bundle" in formats and b["bundle_doc"] is not None:
            jpath = out / f"acnlb-{b['name']}.bundle.json"
            data = (json.dumps(b["bundle_doc"], ensure_ascii=False, indent=2) + "\n").encode("utf-8")
            emit(jpath, data)
            artifacts.append({"path": jpath.name, "bytes": len(data), "sha256": sha256(data)})
        manifest_bundles.append({
            "name": b["name"],
            "kind": b["kind"],
            "source": b["source"],
            "prefix": b["prefix"],
            "count": b["summary"]["count"],
            "total_points": b["summary"]["total_points"],
            "entry_count": sum(1 for arc, _ in b["entries"] if not arc.endswith("/")),
            "artifacts": artifacts,
            "entries": _file_facts(b["entries"], b["prefix"]),
        })

    if "manifest" in formats:
        manifest = {
            "generator": "tools/build_bundle.py",
            "schema_version": SCHEMA_VERSION,
            "commit": args.commit,
            "bundles": manifest_bundles,
        }
        emit(out / "manifest.json",
             (json.dumps(manifest, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))

    if "howto" in formats:
        emit(out / "HOWTO.txt", howto(manifest_bundles, args.commit).encode("utf-8"))

    if "sums" in formats:
        lines = []
        for p in sorted(written, key=lambda p: p.name):
            lines.append(f"{sha256(p.read_bytes())}  {p.name}")
        (out / "SHA256SUMS").write_text("\n".join(lines) + "\n", encoding="utf-8")
        written.append(out / "SHA256SUMS")

    for p in sorted(written, key=lambda p: p.name):
        print(f"{rel(p)}  {p.stat().st_size} bytes")
    for m in manifest_bundles:
        print(f"  {m['name']}: {m['count']} items, {m['total_points']:g} points, "
              f"{m['entry_count']} files")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
