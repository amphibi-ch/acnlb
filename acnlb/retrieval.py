"""Retrieval scoring — the section 2.6 graded-relevance path.

US retrieval gold is "the passage that answers the query." CN retrieval gold is
fuzzy: 类案检索 is graded 高/中/低 on 案由 match, 争议焦点 match, and 裁判规则
match. This module is a SECOND scoring path, used only by retrieval items that
carry a ``retrieval_gold`` block. Everything else goes through ``scorer.py``
unchanged.

For a retrieval item, the final score is the sum of:
  * partial credit from relevance-tier matches (this module), and
  * the ordinary affirmative-minus-negative rubric path (``scorer.py``),
both floored at 0 across the total.

A graded retrieval item needs two agreeing reviewers to fix the tiers, so the
sample set keeps exactly one such item; the README says so.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field

from .scorer import ItemScore
from .schema import RetrievalGold


@dataclass
class TierMatch:
    ref: str
    gold_tier: str
    matched: bool
    awarded: float


@dataclass
class RetrievalScore:
    item_id: str
    klass: str
    awarded: float
    max_awardable: float
    matches: list[TierMatch] = field(default_factory=list)

    def as_dict(self) -> dict:
        return {
            "item_id": self.item_id,
            "class": self.klass,
            "awarded": round(self.awarded, 6),
            "max_awardable": round(self.max_awardable, 6),
            "matches": [
                {"ref": m.ref, "gold_tier": m.gold_tier, "matched": m.matched,
                 "awarded": round(m.awarded, 6)}
                for m in self.matches
            ],
        }


def _norm(s: str) -> str:
    """Drop whitespace and CJK/latin punctuation so 「第 585 条」== 「第585条」."""
    return "".join(ch for ch in s.lower() if ch.isalnum() or "一" <= ch <= "鿿")


def _contains(haystack: str, needle: str) -> bool:
    return _norm(needle) in _norm(haystack)


_ARTICLE = re.compile(r"第[0-9〇零一二三四五六七八九十百千]+条")


def _ref_parts(ref: str) -> list[str]:
    """Split a gold ref into the mandatory parts that must all appear.

    A statute ref like ``《民法典》第585条`` is rarely written contiguously — the
    law name and the article number land on separate lines. So we require each
    part to appear somewhere, rather than one contiguous substring. Case refs
    (``（2021）最高法民申1234号``) stay whole.
    """
    m = _ARTICLE.search(ref)
    if not m:
        return [ref]
    article = m.group(0)
    law = ref[: m.start()]
    parts = [article]
    if law.strip("《》　 ()（）"):
        parts.insert(0, law)
    return parts


def _ref_matches(ref: str, haystack: str) -> bool:
    return all(_contains(haystack, part) for part in _ref_parts(ref))


def score_retrieval(
    item_id: str,
    gold: RetrievalGold,
    *,
    surfaced_refs: list[str] | None = None,
    response_text: str = "",
) -> RetrievalScore:
    """Award partial credit for gold items the response surfaces.

    ``surfaced_refs`` is the reviewer/judge-extracted list of references the
    response returned (case number, article number, document id). If omitted,
    ``response_text`` is scanned for each gold ref directly. Pure given inputs.
    """
    surfaced = surfaced_refs or []
    awarded = 0.0
    max_award = 0.0
    matches: list[TierMatch] = []

    for g in gold.gold_items:
        pts = gold.tier_points.get(g.tier, 0.0)
        max_award += pts
        matched = any(_contains(ref, g.ref) or _ref_matches(g.ref, ref) for ref in surfaced)
        if not matched and response_text:
            matched = _ref_matches(g.ref, response_text)
        if matched:
            awarded += pts
        matches.append(TierMatch(ref=g.ref, gold_tier=g.tier, matched=matched, awarded=pts if matched else 0.0))

    return RetrievalScore(
        item_id=item_id,
        klass=gold.klass,
        awarded=round(awarded, 6),
        max_awardable=round(max_award, 6),
        matches=matches,
    )


def combine(item_score: ItemScore, retrieval: RetrievalScore | None) -> ItemScore:
    """Fold relevance credit into an ItemScore, re-flooring the total at 0."""
    if retrieval is None:
        return item_score
    earned = item_score.affirmative_earned + retrieval.awarded
    maxp = item_score.affirmative_max + retrieval.max_awardable
    raw = earned - item_score.negative_total
    item_score.affirmative_earned = round(earned, 6)
    item_score.affirmative_max = round(maxp, 6)
    item_score.raw_score = round(raw, 6)
    item_score.score = round(max(raw, 0.0), 6)
    return item_score
