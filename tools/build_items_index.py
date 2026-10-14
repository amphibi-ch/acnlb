"""Write site/items.json — a flat, display-only index of the benchmark set.

The site has no build step: index.html + app.js read this file to render the
item table in the "测评题集" section. Re-run it whenever items change.

It also carries `vocab`: the values the set already uses for `category`,
`task_type`, `jurisdiction`, `authority_basis` and document paths, plus the next
free id per prefix. Those fields are free strings in the schema on purpose — the
set may grow a category nobody anticipated — so the answer to "what should I put
here" cannot come from the schema. It comes from the items that already exist,
and it is derived in `acnlb.vocab` so the web form and the issue-to-PR tool
cannot disagree about what the next `core-tx-` id is.

Run:  python tools/build_items_index.py
      python tools/build_items_index.py --items items/real --out site/items.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # tools/ is not a package; run as a script
    sys.path.insert(0, str(ROOT))

from acnlb.schema import TRACK_LABELS  # noqa: E402
from acnlb.vocab import build_vocab  # noqa: E402


def rel(path: Path) -> str:
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build(items_dir: Path) -> dict:
    items = []
    raws: list[dict] = []
    for path in sorted(items_dir.glob("*.json")):
        if path.name.startswith("_"):  # _template.item.json etc.
            continue
        d = json.loads(path.read_text(encoding="utf-8"))
        raws.append(d)
        track = d.get("track") or ""
        items.append({
            "id": d.get("id") or path.stem,
            "track": track,
            "track_label": TRACK_LABELS.get(track, track),
            "category": d.get("category") or "",
            "task_type": d.get("task_type") or "",
            "task": d.get("task") or "",
            "points": d.get("max_positive_points") or 0,
            "documents": len(d.get("documents") or []),
            "authority_basis": d.get("authority_basis") or [],
        })
    return {
        "source": rel(items_dir),
        "count": len(items),
        "total_points": sum(i["points"] for i in items),
        "items": items,
        "vocab": build_vocab(raws),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--items", default="items/bench10", help="item directory to index")
    ap.add_argument("--out", default="site/items.json", help="output JSON path")
    args = ap.parse_args()

    items_dir = (ROOT / args.items).resolve()
    out = (ROOT / args.out).resolve()
    if not items_dir.is_dir():
        print(f"error: {items_dir} is not a directory")
        return 1

    data = build(items_dir)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"{rel(out)}: {data['count']} items, {data['total_points']:g} points")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
