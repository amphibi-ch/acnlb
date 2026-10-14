"""Scaffolding from an intake form, including the retrieval gold section.

Before this section existed, a retrieval item's graded gold had to be hand-edited
into the generated JSON after scaffolding — so the one field the retrieval track is
scored against was also the one field no tool checked. Now it is part of the form,
and a retrieval item that omits it is refused before any file is written.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb.scaffold import parse_gold_block, parse_intake, scaffold  # noqa: E402
from acnlb.schema import Item  # noqa: E402

RETRIEVAL_OK = """id: ret-9101
track: retrieval
task_type: 法条检索
task: 检索违约金司法调整规则的现行依据
has_context: false
authority_basis: 《民法典》第585条

## Prompt

请给出法律名称与条文序号。

## Gold answer

《民法典》第585条。

## Retrieval gold

class: statute

- 高 | 《民法典》第585条 | 现行直接依据
- 中 | 《民法典》第577条 | 一般规定
"""

RETRIEVAL_MISSING = """id: ret-9102
track: retrieval
task_type: 法条检索
task: 忘了写检索基准
has_context: false

## Prompt

请检索。

## Gold answer

（参考答案。）
"""

CORE_WITH_STRAY_GOLD = """id: core-tx-9103
track: core
task_type: 合同审查
task: 从模板抄来的整段
has_context: false

## Prompt

请审查。

## Gold answer

（参考答案。）

## Retrieval gold

class: statute

- 高 | 《民法典》第585条 | 本段应被忽略
"""


def test_retrieval_intake_writes_the_gold_block(tmp_path: Path) -> None:
    intake = tmp_path / "in.md"
    intake.write_text(RETRIEVAL_OK, encoding="utf-8")
    written, warnings = scaffold(intake, tmp_path / "items")

    # The skeleton rubric is not used here, so the only thing a warning may be
    # about is the retrieval gold section itself.
    assert not any("Retrieval gold" in w for w in warnings), warnings
    assert sorted(p.name for p in written) == [
        "ret-9101.json", "ret-9101.md", "ret-9101.rubric.md",
    ]
    assert (tmp_path / "items" / "gold" / "ret-9101.md").is_file()

    item = Item.load(tmp_path / "items" / "ret-9101.json")
    assert item.retrieval_gold is not None
    assert item.retrieval_gold.klass == "statute"
    assert [(g.tier, g.ref) for g in item.retrieval_gold.gold_items] == [
        ("高", "《民法典》第585条"),
        ("中", "《民法典》第577条"),
    ]
    assert item.retrieval_gold.tier_points == {"高": 2.0, "中": 1.0, "低": 0.5}


def test_retrieval_intake_without_gold_fails_before_writing(tmp_path: Path) -> None:
    intake = tmp_path / "in.md"
    intake.write_text(RETRIEVAL_MISSING, encoding="utf-8")
    out = tmp_path / "items"

    with pytest.raises(ValueError, match="Retrieval gold"):
        scaffold(intake, out)
    # The point of failing here rather than in Item.from_dict: no half-written
    # item directory is left behind for a later `validate` to trip over.
    assert not out.exists() or not list(out.glob("*.json"))


def test_stray_gold_section_on_other_tracks_is_dropped_loudly(tmp_path: Path) -> None:
    """The intake template carries the section for both tracks; pasting all of it works."""
    intake = tmp_path / "in.md"
    intake.write_text(CORE_WITH_STRAY_GOLD, encoding="utf-8")
    written, warnings = scaffold(intake, tmp_path / "items")

    assert any("Retrieval gold" in w for w in warnings), warnings
    item = Item.load(tmp_path / "items" / "core-tx-9103.json")
    assert item.retrieval_gold is None
    assert "retrieval_gold" not in json.loads((tmp_path / "items" / "core-tx-9103.json").read_text("utf-8"))


def test_gold_block_rejects_bad_input() -> None:
    with pytest.raises(ValueError, match="class"):
        parse_gold_block("- 高 | 《民法典》第585条 | 无 class 行")
    with pytest.raises(ValueError, match="tier"):
        parse_gold_block("class: statute\n- 极高 | 《民法典》第585条 | x")
    with pytest.raises(ValueError, match="<tier>"):
        parse_gold_block("class: statute\n- 只有一段")
    with pytest.raises(ValueError, match="no ref"):
        parse_gold_block("class: statute\n- 高 |  | 空依据")

    klass, items = parse_gold_block("class: similar_case\n- 中 | （2020）京民终1号")
    assert klass == "similar_case"
    assert items == [("中", "（2020）京民终1号", "")]


def test_intake_section_vocabulary_is_exported_for_the_form() -> None:
    """The web form offers these headings, so they must be the parser's own list."""
    from acnlb.scaffold import GOLD_SECTIONS, INTAKE_SECTIONS, RETRIEVAL_SECTIONS

    lowered = {s.lower() for s in INTAKE_SECTIONS}
    assert {"prompt", "documents", "rubric", "notes"} <= lowered
    assert "gold answer" in lowered
    assert "retrieval gold" in lowered
    assert set(GOLD_SECTIONS) <= set(INTAKE_SECTIONS)
    assert set(RETRIEVAL_SECTIONS) <= set(INTAKE_SECTIONS)

    parsed = parse_intake(
        "## Prompt\n\np\n\n"
        "## Documents\n\n- a.md\n\n"
        "## Gold answer\n\ng\n\n"
        "## Retrieval gold\n\nclass: statute\n\n- 高 | X | n\n"
    )
    assert parsed.prompt == "p"
    assert parsed.documents == ["a.md"]
    assert parsed.gold == "g"
    assert parsed.retrieval_gold == ("statute", [("高", "X", "n")])
