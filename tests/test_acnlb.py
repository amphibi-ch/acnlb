"""Determinism, relevance, kappa, and schema tests.

The load-bearing one is ``test_score_is_deterministic``: scoring the same fixture
twice must be byte-identical (design doc section 3.8).
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb import negatives  # noqa: E402
from acnlb.judge import cohens_kappa  # noqa: E402
from acnlb.retrieval import article_number, score_retrieval  # noqa: E402
from acnlb.rubric import parse_rubric_file, render_worksheet, validate_rubric  # noqa: E402
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


@pytest.mark.parametrize(
    "written, want",
    [("585", 585), ("五百八十五", 585), ("一百零一", 101), ("十", 10),
     ("二十", 20), ("一千二百三十四", 1234), ("一万", 10000), ("〇", 0),
     ("abc", None), ("", None)],
)
def test_article_number_reads_both_numeral_systems(written, want):
    assert article_number(written) == want


def test_retrieval_matches_a_cjk_numeral_article():
    """Regression: 「第五百八十五条」 and 「第585条」 are the same article.

    Judgments and 司法解释 write 条 in CJK numerals; the gold set writes Arabic.
    Substring matching scored the first as a miss, so a model that answered
    correctly — like the local-cli run that prompted this — silently lost the
    point, always in the same direction.
    """
    item = next(i for i in _items() if i.id == "ret-0009")
    gold = item.retrieval_gold
    response = "法律名称：《中华人民共和国民法典》\n条文序号：**第五百八十五条**"
    rs = score_retrieval(item.id, gold, response_text=response)
    assert rs.awarded == 2.0
    assert [m.matched for m in rs.matches] == [True]


def test_retrieval_rejects_a_neighbouring_article_or_law():
    """The numeral fix must not turn the matcher into 'any article will do'."""
    item = next(i for i in _items() if i.id == "ret-0009")
    gold = item.retrieval_gold
    other_article = score_retrieval(
        item.id, gold, response_text="依据《民法典》第五百八十六条的规定")
    other_law = score_retrieval(
        item.id, gold, response_text="依据《刑法》第五百八十五条的规定")
    for rs in (other_article, other_law):
        assert rs.awarded == 0.0
        assert [m.matched for m in rs.matches] == [False]


def test_kappa_perfect_and_chance():
    assert cohens_kappa([True, False, True], [True, False, True])[0] == pytest.approx(1.0)
    k, _ = cohens_kappa([True, True, True], [False, False, False])
    assert k == pytest.approx(0.0)


def test_rubric_parser_reads_affirmative_section():
    """Regression: `## Affirmative Points` must not swallow the affirmative lines."""
    rubric = parse_rubric_file(SAMPLE / "core-lit-0005.rubric.md")
    assert len(rubric.affirmative) >= 6
    assert rubric.max_positive_points == 9


def test_worksheet_verdicts_block_is_valid_json():
    """Regression: the block a reviewer pastes must parse as-is.

    It used to end every entry with a comma, including the last one, so the
    worksheet handed out `Illegal trailing comma before end of object`.
    """
    for rubric_path in sorted(SAMPLE.glob("*.rubric.md")):
        rubric = parse_rubric_file(rubric_path)
        md = render_worksheet(rubric_path.stem, rubric)
        block = re.search(r"```json\n(.*?)\n```", md, re.S).group(1)
        verdicts = json.loads(block)  # raises if the trailing comma comes back
        assert verdicts["item_id"] == rubric_path.stem
        assert set(verdicts["affirmative"]) == {p.key for p in rubric.affirmative}
        assert set(verdicts["negative"]) == {n.key for n in rubric.negative}
