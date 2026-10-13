"""Generate good/bad verdicts sidecars from each item's rubric.

Keys must match the rubric parser exactly, so we derive them rather than hand-typing.
Run:  ./.venv/bin/python tools/make_verdicts.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from acnlb.rubric import parse_rubric_file  # noqa: E402
from acnlb.schema import load_items  # noqa: E402
from acnlb.scorer import score  # noqa: E402

SAMPLE = ROOT / "items" / "sample"
FIX = SAMPLE / "fixtures"

# item_id -> kwargs: set (pass) / clear (fail), and negative code -> (good,bad) counts.
# Semantics: each set lists the affirmative points the response FAILS (is not hit).
# Sentinels: "__all_pass__" (hit everything), "__all_fail__" (hit nothing),
# "__all_but_585__" (hit everything except the 585-adjustment item).
GOOD_PASS: dict[str, set[str]] = {
    "core-tx-0001": {"__all_pass__"},
    "core-tx-0002": {"__all_pass__"},
    "core-lit-0003": {"__all_pass__"},
    "core-lit-0004": {"__all_pass__"},
    "core-lit-0005": {"__all_pass__"},
    "wf-0006": {"__all_pass__"},
    "wf-0007": {"__all_pass__"},
    "wf-0008": {"__all_pass__"},
    "ret-0009": {"__all_pass__"},
    "ret-0010": {"__all_pass__"},
}
BAD_PASS: dict[str, set[str]] = {
    "core-tx-0001": {"__all_but_585__"},
    "core-tx-0002": {"__all_fail__"},
    "core-lit-0003": {"__all_fail__"},
    "core-lit-0004": {"__all_fail__"},
    "core-lit-0005": {"__all_fail__"},
    "wf-0006": {"__all_fail__"},
    "wf-0007": {"__all_fail__"},
    "wf-0008": {"__all_fail__"},
    "ret-0009": {"__all_fail__"},
    "ret-0010": {"__all_fail__"},
}
# negative code -> (good_count, bad_count)
NEG_COUNTS: dict[str, dict[str, tuple[int, int]]] = {
    "core-tx-0001": {"HALLUC_FACT": (0, 1), "REPEALED_LAW": (0, 1), "EXTRATEXT": (0, 1)},
    "core-tx-0002": {"REPEALED_LAW": (0, 1)},
    "core-lit-0003": {"REPEALED_LAW": (0, 1)},
    "core-lit-0004": {"WRONG_HIERARCHY": (0, 1)},
    "core-lit-0005": {"REPEALED_LAW": (0, 1), "FORMAT_BREACH": (0, 1)},
    "wf-0006": {"FORMAT_BREACH": (0, 1)},
    "wf-0007": {"FORMAT_BREACH": (0, 1)},
    "wf-0008": {},
    "ret-0009": {"REPEALED_LAW": (0, 1)},
    "ret-0010": {},
}


def pick(points, fail_set: set[str]) -> dict[str, bool]:
    """Return {unique_key: hit}. ``fail_set`` lists points the response does NOT hit.

    Several rubric lines share identical text, so keys are suffixed with '#n' to
    stay unique — otherwise JSON collapses duplicates and affirmative_max reads 0.
    """
    out: dict[str, bool] = {}
    seen: dict[str, int] = {}
    for p in points:
        if "__all_pass__" in fail_set:
            hit = True
        elif "__all_fail__" in fail_set:
            hit = False
        elif "__all_but_585__" in fail_set:
            hit = "585" in p.text
        else:
            first = p.text.split(":")[0]
            hit = not ((first in fail_set) or (p.subsection in fail_set))
        n = seen.get(p.key, 0)
        seen[p.key] = n + 1
        key = p.key if n == 0 else f"{p.key}#{n}"
        out[key] = hit
    return out


def neg_verdicts(neg_points, code_counts: dict[str, tuple[int, int]], which: int) -> dict[str, int]:
    out = {}
    for n in neg_points:
        out[n.key] = code_counts.get(n.code, (0, 0))[which]
    return out


def main() -> int:
    items = {i.id: i for i in load_items(SAMPLE)}
    summary = []
    for iid, item in items.items():
        rubric = parse_rubric_file(SAMPLE / item.rubric)
        for which, name, pass_map in ((0, "good", GOOD_PASS[iid]), (1, "bad", BAD_PASS[iid])):
            aff = pick(rubric.affirmative, pass_map)
            neg = neg_verdicts(rubric.negative, NEG_COUNTS.get(iid, {}), which)
            payload = {"item_id": iid, "source": "manual", "affirmative": aff, "negative": neg}
            (FIX / f"{iid}.{name}.verdicts.json").write_text(
                json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
            )
            s = score(rubric, affirmative=aff, negative=neg)
            summary.append((iid, name, s.score, s.affirmative_max, s.negative_total))
    print(f"{'item':16} {'kind':5} {'score':>6} {'max':>5} {'neg':>5}")
    for iid, name, sc, mx, ng in summary:
        print(f"{iid:16} {name:5} {sc:6g} {mx:5g} {ng:5g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
