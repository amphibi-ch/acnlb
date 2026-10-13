"""Determinism, relevance, kappa, and schema tests.

The load-bearing one is ``test_score_is_deterministic``: scoring the same fixture
twice must be byte-identical (design doc section 3.8).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb import negatives  # noqa: E402
from acnlb.judge import cohens_kappa  # noqa: E402
from acnlb.retrieval import score_retrieval  # noqa: E402
from acnlb.rubric import parse_rubric_file, validate_rubric  # noqa: E402
from acnlb.schema import load_items, validate_item  # noqa: E402
from acnlb.scorer import canonical_json, score  # noqa: E402

SAMPLE = ROOT / "items" / "sample"
FIX = SAMPLE / "fixtures"


def _items():
    return load_items(SAMPLE)


@pytest.mark.parametrize("item", _items(), ids=lambda i: i.id)
def test_sample_items_validate(item):
    problems = validate_item(item, SAMPLE)
    assert not problems, f"{item.id}: {problems}"
    rubric = parse_rubric_file(SAMPLE / item.rubric)
    assert not validate_rubric(rubric, expected_id=item.id)


@pytest.mark.parametrize("item", _items(), ids=lambda i: i.id)
def test_sample_items_are_synthetic(item):
    assert item.is_synthetic, f"{item.id} under items/sample must be marked SYNTHETIC"


@pytest.mark.parametrize("item", _items(), ids=lambda i: i.id)
def test_score_is_deterministic(item):
    """Same (response, verdicts, rubric) -> byte-identical score, twice."""
    verdicts_path = FIX / f"{item.id}.good.verdicts.json"
    if not verdicts_path.exists():
        pytest.skip("no fixture")
    v = json.loads(verdicts_path.read_text(encoding="utf-8"))
    rubric = parse_rubric_file(SAMPLE / item.rubric)
    a = canonical_json(score(rubric, affirmative=v["affirmative"], negative=v["negative"]))
    b = canonical_json(score(rubric, affirmative=v["affirmative"], negative=v["negative"]))
    assert a == b


@pytest.mark.parametrize("item", _items(), ids=lambda i: i.id)
def test_good_beats_bad(item):
    good_p = FIX / f"{item.id}.good.verdicts.json"
    bad_p = FIX / f"{item.id}.bad.verdicts.json"
    if not (good_p.exists() and bad_p.exists()):
        pytest.skip("no fixtures")
    rubric = parse_rubric_file(SAMPLE / item.rubric)
    g = json.loads(good_p.read_text(encoding="utf-8"))
    b = json.loads(bad_p.read_text(encoding="utf-8"))
    gs = score(rubric, affirmative=g["affirmative"], negative=g["negative"])
    bs = score(rubric, affirmative=b["affirmative"], negative=b["negative"])
    assert gs.score > bs.score
    assert gs.score <= gs.affirmative_max


def test_floored_at_zero():
    """A bad answer can be driven below zero on raw points but never scores < 0."""
    item = next(i for i in _items() if i.id == "core-lit-0005")
    rubric = parse_rubric_file(SAMPLE / item.rubric)
    b = json.loads((FIX / "core-lit-0005.bad.verdicts.json").read_text(encoding="utf-8"))
    s = score(rubric, affirmative=b["affirmative"], negative=b["negative"])
    assert s.score == 0.0
    assert s.raw_score < s.score


def test_negative_codes_are_closed():
    for item in _items():
        rubric = parse_rubric_file(SAMPLE / item.rubric)
        for n in rubric.negative:
            assert n.code in negatives.CODES, f"{item.id}: {n.code}"


def test_retrieval_graded_relevance():
    item = next(i for i in _items() if i.id == "ret-0010")
    rs = score_retrieval(
        item.id, item.retrieval_gold,
        surfaced_refs=["（2021）最高法民申1234号", "（2019）沪民初9012号"],
    )
    # 高 (2.0) + 低 (0.5) = 2.5
    assert rs.awarded == 2.5
    assert rs.max_awardable == 3.5


def test_kappa_perfect_and_chance():
    assert cohens_kappa([True, False, True], [True, False, True])[0] == pytest.approx(1.0)
    k, _ = cohens_kappa([True, True, True], [False, False, False])
    assert k == pytest.approx(0.0)


def test_rubric_parser_reads_affirmative_section():
    """Regression: `## Affirmative Points` must not swallow the affirmative lines."""
    rubric = parse_rubric_file(SAMPLE / "core-lit-0005.rubric.md")
    assert len(rubric.affirmative) >= 6
    assert rubric.max_positive_points == 9
