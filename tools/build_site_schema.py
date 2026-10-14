"""Export the item schema as JSON, so the web form validates like the CLI does.

The site now lets a drafter author an item in a browser and download the exact
files `acnlb new --intake` would have written. For that to be safe the form has
to reject precisely what ``Item.from_dict`` rejects, and pre-fill precisely the
rubric skeleton and negative taxonomy ``acnlb new`` pre-fills.

Re-typing those constants in JavaScript is how the two drift, and the failure is
silent in the worst direction: the form happily produces a directory the CLI
refuses, in somebody else's checkout, at commit time. So the constants are
exported from the package that owns them and the page fetches the export.

Run:  python tools/build_site_schema.py
      python tools/build_site_schema.py --out site/schema.json
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # tools/ is not a package; run as a script
    sys.path.insert(0, str(ROOT))

from acnlb import SCHEMA_VERSION  # noqa: E402
from acnlb import negatives  # noqa: E402
from acnlb.schema import (  # noqa: E402
    DEFAULT_TIER_POINTS,
    ID_HINT,
    ID_PATTERN,
    REQUIRED_FIELDS,
    RETRIEVAL_CLASSES,
    TRACK_LABELS,
    VALID_TIERS,
    VALID_TRACKS,
)
from acnlb.scaffold import (  # noqa: E402
    DEFAULT_RUBRIC,
    GOLD_SECTIONS,
    INTAKE_SECTIONS,
    RETRIEVAL_SECTIONS,
    RUBRIC_LAYOUT,
    RUBRIC_TEMPLATES,
)


def build() -> dict:
    return {
        "schema_version": SCHEMA_VERSION,
        "required_fields": list(REQUIRED_FIELDS),
        "valid_tracks": sorted(VALID_TRACKS),
        "track_labels": TRACK_LABELS,
        "valid_tiers": sorted(VALID_TIERS),
        "tier_points": DEFAULT_TIER_POINTS,
        "retrieval_classes": list(RETRIEVAL_CLASSES),
        "negatives": [
            {
                "code": c.code,
                "points": c.points,
                "label_zh": c.label_zh,
                "label_en": c.label_en,
                "description": c.description,
                "task_defined": c.code in negatives.TASK_DEFINED,
            }
            for c in negatives.TAXONOMY
        ],
        "default_rubric": DEFAULT_RUBRIC,
        "rubric_templates": RUBRIC_TEMPLATES,
        "rubric_layout": RUBRIC_LAYOUT,
        "intake_sections": list(INTAKE_SECTIONS),
        "gold_sections": list(GOLD_SECTIONS),
        "retrieval_sections": list(RETRIEVAL_SECTIONS),
        "paths": {
            "gold_dir": "gold",
            "item_suffix": ".json",
            "rubric_suffix": ".rubric.md",
        },
        # Soft rules, deliberately: `id` and `document.path` are free strings in
        # the item schema, and these are the two places it is turned into a path.
        # The form applies the same checks the CLI does so the page cannot accept
        # what `validate` would refuse.
        "id_pattern": ID_PATTERN,
        "id_hint": ID_HINT,
    }


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--out", default="site/schema.json", help="output JSON path")
    args = ap.parse_args()

    out = (ROOT / args.out).resolve()
    out.parent.mkdir(parents=True, exist_ok=True)
    data = build()
    out.write_text(json.dumps(data, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(
        f"{rel(out)}: {len(data['negatives'])} negative codes, "
        f"{len(data['valid_tracks'])} tracks, schema {data['schema_version']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
