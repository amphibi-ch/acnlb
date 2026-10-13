"""Cache-bust the CSS/JS URLs in a built index.html, in place.

GitHub Pages serves static assets with `Cache-Control: max-age=600`, and the URL
of index.html itself never changes — so a browser that already cached app.js or
styles.css keeps running them for ten minutes after a deploy. That is plenty of
time to load a fresh index.html driven by a stale app.js: sections render empty
and links point at old paths, with nothing in the console to explain it.

Rewriting the asset URLs with a content hash gives every deploy a new URL, so the
cache is bypassed exactly when the file changed and reused when it did not.

The source site/index.html stays clean; only the deployed copy is stamped.

Run:  python tools/stamp_assets.py _site/index.html
      python tools/stamp_assets.py _site/index.html --assets styles.css app.js
"""
from __future__ import annotations

import argparse
import hashlib
import re
from pathlib import Path


def digest(path: Path) -> str:
    return hashlib.sha1(path.read_bytes()).hexdigest()[:10]


def stamp(html: str, name: str, version: str) -> tuple[str, int]:
    """Point every reference to `name` at `<name>?v=<version>`."""
    pattern = re.compile(
        r'(["\'])([^"\']*?/)?' + re.escape(name) + r'((?:\?v=[0-9a-f]+)?)(["\'])'
    )

    def repl(m: re.Match[str]) -> str:
        return f"{m.group(1)}{m.group(2) or ''}{name}?v={version}{m.group(4)}"

    return pattern.subn(repl, html)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("page", help="built index.html to stamp in place")
    ap.add_argument("--assets", nargs="+", default=["styles.css", "app.js"])
    args = ap.parse_args()

    page = Path(args.page)
    html = page.read_text(encoding="utf-8")
    done: list[str] = []

    for name in args.assets:
        asset = page.parent / name
        if not asset.is_file():
            print(f"skip {name}: not found next to {page}")
            continue
        version = digest(asset)
        html, n = stamp(html, name, version)
        if n:
            done.append(f"{name}?v={version} ({n} ref{'s' if n > 1 else ''})")

    page.write_text(html, encoding="utf-8")
    print("stamped " + ", ".join(done) if done else "nothing stamped")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
