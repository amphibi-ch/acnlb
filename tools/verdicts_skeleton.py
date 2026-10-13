"""Write empty verdicts files for an items dir — one per item, keys pre-filled.

Grading by hand means retyping the rubric's exact key strings
(``aff:Substance:是否准确指向《民法典》第585条…``) into JSON. One character off
and that line silently scores as missed, with no error anywhere. So the keys come
from the rubric parser instead of from a human.

Values are deliberately left at fail/zero: this removes the typing, it does not
make a judgement. ``source`` stays ``"manual"`` — a filled-in file must say what
actually graded the answers.

Run:
    python tools/verdicts_skeleton.py --items items/bench10 --out runs/verdicts
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb.rubric import parse_rubric_file  # noqa: E402
from acnlb.schema import load_items  # noqa: E402


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="items/bench10", help="items directory")
    ap.add_argument("--out", default="runs/verdicts", help="where <id>.verdicts.json goes")
    ap.add_argument("--force", action="store_true", help="overwrite files that already exist")
    args = ap.parse_args()

    items_root = (ROOT / args.items).resolve()
    out = (ROOT / args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)

    written = kept = 0
    for item in load_items(items_root):
        dest = out / f"{item.id}.verdicts.json"
        if dest.exists() and not args.force:
            kept += 1
            continue
        rubric = parse_rubric_file(items_root / item.rubric)
        payload = {
            "item_id": item.id,
            "source": "manual",
            "judge_model": "",
            "affirmative": {p.key: False for p in rubric.affirmative},
            "negative": {n.key: 0 for n in rubric.negative},
        }
        dest.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
                        encoding="utf-8")
        written += 1
        print(f"{item.id}: {len(rubric.affirmative)} affirmative + {len(rubric.negative)} negative")

    try:
        shown = out.relative_to(ROOT)
    except ValueError:
        shown = out
    print(f"\nwrote {written} file(s) → {shown}" + (f"; kept {kept} existing" if kept else ""))
    print("Values are all fail/zero — filling them IS the grading. Do not publish a run "
          "scored from these before you do.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
