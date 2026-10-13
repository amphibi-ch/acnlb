"""Scoring (design doc section 3.8). PURE and deterministic.

    score = Σ(affirmative points hit) − Σ(negative points), floored at 0

Given the same ``(response, rubric, verdicts)`` this returns the same number
byte-for-byte, every run, on every machine: no clock, no randomness, no I/O.
Model inference lives in ``runner.py`` and is cached, so re-scoring after a
rubric tweak never triggers new inference.

Two verdict sources feed this module:
  - a human verdicts file (``--judge manual``), or
  - an LLM judge (``--judge llm``), which emits the same verdict shape.

Either way the arithmetic below is the same and is the only place scores are
computed.
"""

from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path

from .rubric import AffirmativePoint, NegativePoint, Rubric


@dataclass
class AffirmativeVerdict:
    key: str
    hit: bool
    points: float


@dataclass
class NegativeVerdict:
    key: str
    code: str
    count: int
    points: float  # magnitude per occurrence
    subtotal: float  # count * points, positive


@dataclass
class ItemScore:
    item_id: str
    track: str
    affirmative_earned: float
    affirmative_max: float
    negative_total: float  # positive magnitude of the deduction
    raw_score: float
    score: float  # floored at 0
    affirmative: list[AffirmativeVerdict] = field(default_factory=list)
    negative: list[NegativeVerdict] = field(default_factory=list)
    rubric_hash: str = ""

    def as_dict(self) -> dict:
        return asdict(self)


def _norm_key(s: str) -> str:
    return " ".join(s.split()).strip().lower()


def _index_affirmative(rubric: Rubric) -> dict[str, AffirmativePoint]:
    idx: dict[str, AffirmativePoint] = {}
    for p in rubric.affirmative:
        idx[_norm_key(p.key)] = p
        # also index by bare text so a hand-written verdicts file can omit the prefix
        idx.setdefault(_norm_key(p.text), p)
    return idx


def _index_negative(rubric: Rubric) -> dict[str, NegativePoint]:
    idx: dict[str, NegativePoint] = {}
    for n in rubric.negative:
        idx[_norm_key(n.key)] = n
        idx.setdefault(_norm_key(n.text), n)
        idx.setdefault(_norm_key(n.code), n)
    return idx


def score(
    rubric: Rubric,
    *,
    affirmative: dict[str, bool] | None = None,
    negative: dict[str, int] | None = None,
) -> ItemScore:
    """Compute an :class:`ItemScore`. Pure.

    ``affirmative`` maps a rubric-line key (or its bare text) to True/False.
    ``negative`` maps a negative line key, its bare text, or a bare taxonomy
    code to an occurrence count. Missing affirmative entries count as not-hit;
    missing negative entries count as zero. Unknown keys are ignored (they do
    not silently match) — callers that care should diff keys first.
    """
    affirmative = affirmative or {}
    negative = negative or {}

    aff_idx = _index_affirmative(rubric)
    neg_idx = _index_negative(rubric)

    aff_verdicts: list[AffirmativeVerdict] = []
    earned = 0.0
    seen_aff: set[str] = set()
    for key, val in affirmative.items():
        p = aff_idx.get(_norm_key(key))
        if p is None:
            continue
        if id(p) in seen_aff:
            continue
        seen_aff.add(id(p))
        if val:
            earned += p.points
        aff_verdicts.append(AffirmativeVerdict(key=p.key, hit=bool(val), points=p.points))
    # include rubric lines with no explicit verdict as not-hit, for a complete report
    for p in rubric.affirmative:
        if id(p) not in seen_aff:
            aff_verdicts.append(AffirmativeVerdict(key=p.key, hit=False, points=p.points))

    neg_verdicts: list[NegativeVerdict] = []
    deduction = 0.0
    seen_neg: set[str] = set()
    for key, count in negative.items():
        n = neg_idx.get(_norm_key(key))
        if n is None or not count:
            continue
        if id(n) in seen_neg:
            continue
        seen_neg.add(id(n))
        sub = float(count) * n.points
        deduction += sub
        neg_verdicts.append(
            NegativeVerdict(
                key=n.key, code=n.code, count=int(count), points=n.points, subtotal=sub
            )
        )

    raw = earned - deduction
    return ItemScore(
        item_id=rubric.item_id,
        track="",  # filled by the caller from the item
        affirmative_earned=round(earned, 6),
        affirmative_max=rubric.max_positive_points,
        negative_total=round(deduction, 6),
        raw_score=round(raw, 6),
        score=round(max(raw, 0.0), 6),
        affirmative=aff_verdicts,
        negative=neg_verdicts,
        rubric_hash=rubric.rubric_hash(),
    )


def score_from_file(response_path: str | Path, rubric: Rubric, verdicts: dict) -> ItemScore:
    """Convenience wrapper used by the ``score`` CLI. Still pure given inputs."""
    return score(
        rubric,
        affirmative=verdicts.get("affirmative", {}),
        negative=verdicts.get("negative", {}),
    )


def canonical_json(obj) -> str:
    """Stable JSON rendering used for byte-identical determinism checks."""
    if hasattr(obj, "as_dict"):
        obj = obj.as_dict()
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, indent=2, separators=(",", ": "))
