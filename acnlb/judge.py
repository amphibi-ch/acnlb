"""Grading (design doc section 3.7): human-first, then an UNVALIDATED LLM judge.

Two modes:

``manual``
    Score from a human verdicts file. ``run --judge manual`` exports a worksheet
    (``rubric.render_worksheet``) when no verdicts file is given, and consumes
    one when it is. This is the reference path.

``llm``
    Ask a judge model, for each ``Does the response state X?`` rubric item,
    whether the response states it — binary yes/no — with the gold answer in
    the judge's context. The judge emits the SAME verdict shape as a human
    verdicts file, so scoring is identical. It is marked **UNVALIDATED** and
    stays so until a labeled agreement set is supplied and Cohen's kappa is
    computed with ``judge-validate``. An unvalidated judge is a convenience,
    never a basis for a model decision (design doc section 4.4).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from .rubric import Rubric, AffirmativePoint, NegativePoint
from .schema import Item

VALIDATION_NOTE = (
    "UNVALIDATED: the LLM judge has no measured agreement with human graders. "
    "Treat its scores as provisional until judge-validate reports kappa >= your "
    "threshold on a labeled set."
)

JUDGE_SYSTEM_PROMPT = """\
You are a strict legal-grading assistant for a Chinese-law benchmark. You are \
given (1) a gold answer written by a competent lawyer, (2) a model response to \
be graded, and (3) a list of atomic rubric items phrased as propositions.

For each affirmative rubric item, decide only whether the RESPONSE states that \
proposition. Do not reward paraphrases that change the legal claim. Answer \
"true" if the response clearly states it, otherwise "false".

For each negative rubric category, count how many times the RESPONSE commits \
that error (0 if none). Base counts on what the response actually says, not on \
what a good answer would avoid. Judge only against the gold answer and the \
rubric; do not add your own legal analysis.

Return ONLY a JSON object of the form:
{"affirmative": {"<item key>": true|false, ...}, "negative": {"<code or key>": <int>, ...}}
"""


@dataclass
class Verdicts:
    item_id: str
    affirmative: dict[str, bool] = field(default_factory=dict)
    negative: dict[str, int] = field(default_factory=dict)
    source: str = "manual"  # "manual" | "llm"
    judge_model: str = ""

    def as_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "source": self.source,
            "judge_model": self.judge_model,
            "affirmative": self.affirmative,
            "negative": self.negative,
        }

    @classmethod
    def load(cls, path: str | Path) -> "Verdicts":
        d = json.loads(Path(path).read_text(encoding="utf-8"))
        return cls(
            item_id=d.get("item_id", ""),
            affirmative={str(k): bool(v) for k, v in d.get("affirmative", {}).items()},
            negative={str(k): int(v) for k, v in d.get("negative", {}).items()},
            source=d.get("source", "manual"),
            judge_model=d.get("judge_model", ""),
        )


# --------------------------------------------------------------------------- #
# manual
# --------------------------------------------------------------------------- #

def load_verdicts(path: str | Path) -> Verdicts:
    return Verdicts.load(path)


# --------------------------------------------------------------------------- #
# llm (unvalidated)
# --------------------------------------------------------------------------- #

def build_judge_prompt(item: Item, rubric: Rubric, response_text: str, gold_text: str) -> str:
    lines = [JUDGE_SYSTEM_PROMPT, "", "=== GOLD ANSWER ===", gold_text.strip(), ""]
    lines.append("=== RESPONSE TO GRADE ===")
    lines.append(response_text.strip())
    lines.append("")
    lines.append("=== AFFIRMATIVE RUBRIC ITEMS ===")
    for p in rubric.affirmative:
        lines.append(f"- key: {json.dumps(p.key, ensure_ascii=False)} :: {p.text} ({p.points:g} pt)")
    lines.append("")
    lines.append("=== NEGATIVE RUBRIC CATEGORIES ===")
    for n in rubric.negative:
        lines.append(f"- key: {json.dumps(n.key, ensure_ascii=False)} :: [{n.code}] {n.text}")
    return "\n".join(lines)


def parse_judge_output(item_id: str, raw: str, rubric: Rubric, judge_model: str) -> Verdicts:
    """Parse the judge's JSON, tolerating a fenced block. Unknown keys dropped."""
    text = raw.strip()
    if text.startswith("```"):
        text = text.split("```", 2)[1]
        if text.lstrip().lower().startswith("json"):
            text = text.lstrip()[4:]
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError(f"judge returned no JSON object: {raw[:200]!r}")
    data = json.loads(text[start : end + 1])
    return Verdicts(
        item_id=item_id,
        affirmative={str(k): bool(v) for k, v in data.get("affirmative", {}).items()},
        negative={str(k): int(v) for k, v in data.get("negative", {}).items()},
        source="llm",
        judge_model=judge_model,
    )


# --------------------------------------------------------------------------- #
# judge validation (Cohen's kappa)
# --------------------------------------------------------------------------- #

@dataclass
class KappaReport:
    n: int
    kappa: float
    agreement: float
    per_item: dict[str, float] = field(default_factory=dict)
    validated: bool = False

    def as_dict(self) -> dict:
        return {
            "n": self.n,
            "kappa": round(self.kappa, 4),
            "agreement": round(self.agreement, 4),
            "per_item": {k: round(v, 4) for k, v in self.per_item.items()},
            "validated": self.validated,
        }


def cohens_kappa(labels_a: list, labels_b: list) -> tuple[float, float]:
    """Cohen's kappa for two label lists (binary or short categorical).

    Returns ``(kappa, observed_agreement)``. Kappa is 0 when expected agreement
    is 1 (degenerate), matching the usual convention.
    """
    if len(labels_a) != len(labels_b):
        raise ValueError("label lists differ in length")
    n = len(labels_a)
    if n == 0:
        return 0.0, 0.0
    cats = sorted({*labels_a, *labels_b}, key=str)
    po = sum(1 for a, b in zip(labels_a, labels_b) if a == b) / n
    pe = 0.0
    for c in cats:
        pa = sum(1 for a in labels_a if a == c) / n
        pb = sum(1 for b in labels_b if b == c) / n
        pe += pa * pb
    kappa = 0.0 if abs(1 - pe) < 1e-12 else (po - pe) / (1 - pe)
    return kappa, po


def validate_judge(labels_path: str | Path, *, min_kappa: float = 0.6) -> KappaReport:
    """Compute kappa between judge and human verdicts on a labeled set.

    ``labels_path`` is a JSON file:
        {"pairs": [{"key": "...", "human": true, "judge": true}, ...]}
    or a list of such objects. The judge is only "validated" when kappa clears
    ``min_kappa``; below that the caller must keep the item in the human bucket.
    """
    data = json.loads(Path(labels_path).read_text(encoding="utf-8"))
    pairs = data["pairs"] if isinstance(data, dict) else data
    human = [p["human"] for p in pairs]
    judge = [p["judge"] for p in pairs]
    kappa, po = cohens_kappa(human, judge)

    per_item: dict[str, float] = {}
    buckets: dict[str, list[tuple]] = {}
    for p in pairs:
        buckets.setdefault(p.get("key", ""), []).append((p["human"], p["judge"]))
    for key, rows in buckets.items():
        if rows:
            per_item[key] = sum(1 for a, b in rows if a == b) / len(rows)

    return KappaReport(
        n=len(pairs), kappa=kappa, agreement=po, per_item=per_item,
        validated=kappa >= min_kappa,
    )
