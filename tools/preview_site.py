#!/usr/bin/env python3
"""Assemble the deployed page into a scratch directory and serve it — deleting nothing.

The deploy workflow assembles `_site/` and starts with `rm -rf _site`. On a
runner that directory is a build product of a throwaway checkout, so the delete
costs nothing. On a working copy it is the removal of a directory the reader did
not create, performed so that they could look at a page. Nobody can tell from
the command whether that directory held only build output, and a preview is not
worth the doubt.

So this runs the same steps the workflow does and writes them into `--out`
(default `runs/preview`, which git already ignores), removing nothing. Run it
again over the same directory and it overwrites what it produces; it also names
the entries it found there that it does not produce, because those are the
leftovers that make a preview show something other than the tree.

It writes nothing outside `--out` either. The deploy regenerates
`site/items.json` and `site/schema.json` in place, which is correct when those
files are the artifact — but a preview must not be able to leave the working
tree dirty, so the two generated data files go straight into the preview.

Run:  python tools/preview_site.py
      python tools/preview_site.py --no-serve
      python tools/preview_site.py --items items/real --out runs/p2 --port 8792
"""
from __future__ import annotations

import argparse
import re
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

# Copied in, plus the three things the assembly adds.
EXTRA_ENTRIES = ("results", "download", ".nojekyll")


def run(*cmd: str) -> None:
    proc = subprocess.run([sys.executable, *cmd], cwd=ROOT, capture_output=True, text=True)
    if proc.returncode != 0:
        raise SystemExit(f"failed: {' '.join(cmd)}\n{proc.stdout}{proc.stderr}")


def commit() -> str:
    proc = subprocess.run(["git", "rev-parse", "HEAD"], cwd=ROOT,
                          capture_output=True, text=True)
    return proc.stdout.strip() if proc.returncode == 0 else ""


def assets_of(page: Path) -> list[str]:
    """The local files index.html loads, read off the page.

    Derived rather than listed, so adding a script to the page cannot leave the
    preview serving an unstamped copy of it — which is the whole failure
    `stamp_assets.py` exists to prevent, reintroduced in the one place nobody
    deploys from.
    """
    html = page.read_text(encoding="utf-8")
    names = re.findall(r'<script src="([^"]+)"', html)
    names += re.findall(r'<link[^>]+href="([^"]+\.(?:css|js))"', html)
    return [n for n in names if not n.startswith(("http", "//", "data:"))]


def assemble(out: Path, items: str) -> list[str]:
    """Mirror deploy-pages.yml into `out`. Returns entries left there untouched."""
    site = ROOT / "site"
    if out.exists() and not out.is_dir():
        raise SystemExit(f"not a directory: {out}")

    produced = {p.name for p in site.iterdir()} | set(EXTRA_ENTRIES)
    foreign = sorted(p.name for p in out.iterdir() if p.name not in produced) \
        if out.is_dir() else []

    out.mkdir(parents=True, exist_ok=True)
    # dirs_exist_ok merges: copy in what is there, delete nothing.
    shutil.copytree(site, out, dirs_exist_ok=True)
    shutil.copytree(ROOT / "results", out / "results", dirs_exist_ok=True)
    (out / ".nojekyll").touch()

    run("tools/build_items_index.py", "--items", items, "--out", str(out / "items.json"))
    run("tools/build_site_schema.py", "--out", str(out / "schema.json"))
    run("tools/build_bundle.py", "--items", items, "--workspace",
        "--out", str(out / "download"), "--commit", commit())
    run("tools/stamp_assets.py", str(out / "index.html"), "--assets", *assets_of(out / "index.html"))
    return foreign


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="items/bench10", help="item set to bundle into the page")
    ap.add_argument("--out", default="runs/preview", help="assembly directory (never emptied)")
    ap.add_argument("--port", type=int, default=8791, help="port for the preview server")
    ap.add_argument("--no-serve", action="store_true", help="assemble only")
    args = ap.parse_args()

    raw = Path(args.out)
    out = raw if raw.is_absolute() else ROOT / raw

    foreign = assemble(out, args.items)
    where = out.relative_to(ROOT) if out.is_relative_to(ROOT) else out
    print(f"assembled into {where}")
    if foreign:
        print("  left untouched — not produced by this assembly:")
        for name in foreign:
            print(f"    {name}")

    if args.no_serve:
        return 0
    port = str(args.port)
    print(f"  http://127.0.0.1:{port}/   (Ctrl-C to stop)")
    return subprocess.run([sys.executable, "-m", "http.server", port, "--bind", "127.0.0.1"],
                          cwd=out).returncode


if __name__ == "__main__":
    raise SystemExit(main())
