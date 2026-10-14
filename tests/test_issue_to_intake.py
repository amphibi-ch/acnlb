"""The issue form as a way in: a stranger fills it in, an Action turns it into
item files and opens a draft pull request.

The submitter has no checkout, no branch and no way to run anything, so the body
they type is the only input and it goes straight into files that a later commit
picks up. Two things follow, and both are tested here rather than trusted:

* the **id becomes a file name** and the **document paths become references the
  items directory has to resolve**, so both are checked before anything is
  written — a `../../etc/passwd` typed into the id field must not become a path;
* the form's field ids and the tool's two lists must stay in step. That is not
  hypothetical: `item_id` was once written by the tool while the form sent `id`,
  and the contributor's id was silently replaced by a generated one.

The template is a YAML file that only GitHub normally reads, so the cross-checks
below are what keeps it honest.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb.scaffold import INTAKE_SECTIONS  # noqa: E402
from acnlb.schema import Item  # noqa: E402
from tools.issue_to_intake import (  # noqa: E402
    HEADER_FIELDS,
    MAX_BODY,
    REFERENCE_SET,
    SECTION_FIELDS,
    ToolError,
    build,
    field_labels,
    load_template,
    one_line,
    parse_issue,
    to_intake,
)

TEMPLATE = ROOT / ".github" / "ISSUE_TEMPLATE" / "new-item.yml"
WORKFLOW = ROOT / ".github" / "workflows" / "item-from-issue.yml"

# GitHub renders the form into the issue body as these labels.
LABELS = {
    "confirm": "确认",
    "id": "编号 id",
    "track": "轨道 track",
    "category": "类别 category",
    "task_type": "任务类型 task_type",
    "task": "任务 task",
    "jurisdiction": "管辖 jurisdiction",
    "documents": "附件路径 documents",
    "authority_basis": "法源依据 authority_basis",
    "prompt": "Prompt",
    "gold": "参考答案 gold answer",
    "rubric": "Rubric",
    "retrieval_gold": "检索基准（仅 retrieval 轨道）",
    "notes": "备注 notes",
}

NO_RESPONSE = "_No response_"

DEFAULTS = {
    "confirm": "- [x] 这是要进 benchmark 的题目（不是提问、不是 bug 报告）",
    "id": NO_RESPONSE,
    "track": "core",
    "category": "Transaction",
    "task_type": "合同审查与风险点识别",
    "task": "审查一份附保证与抵押条款的借款合同",
    "jurisdiction": "CN-mainland",
    "documents": NO_RESPONSE,
    "authority_basis": NO_RESPONSE,
    "prompt": "请审阅随附借款合同并出具审查意见。",
    "gold": "一、保证条款。二、抵押条款。",
    "rubric": NO_RESPONSE,
    "retrieval_gold": NO_RESPONSE,
    "notes": NO_RESPONSE,
}

GOLD = "class: statute\n\n- 高 | 《民法典》第585条 | 违约金调减依据\n- 中 | 《民法典》第577条 | 违约责任一般规定"


def issue_body(**over: str) -> str:
    """A body shaped the way GitHub renders the form."""
    values = dict(DEFAULTS)
    values.update(over)
    parts: list[str] = []
    for key in LABELS:
        parts += [f"### {LABELS[key]}", "", values[key], ""]
    return "\n".join(parts)


def write(tmp_path: Path, name: str, text: str) -> Path:
    path = tmp_path / name
    path.write_text(text, encoding="utf-8")
    return path


def run(tmp_path: Path, body: str, out: str = "items/incoming") -> tuple[dict, Path]:
    out_dir = tmp_path / out
    report = build(body, out_dir, TEMPLATE, intake_out=None)
    return report, out_dir


# ---------- the form and the tool have to agree ----------

def test_the_form_is_a_form_and_carries_the_marker() -> None:
    """The workflow's `if:` keys off this marker, so it has to be in the body."""
    raw = TEMPLATE.read_text(encoding="utf-8")
    assert "<!-- acnlb-item-submission -->" in raw
    assert "<!-- acnlb-item-submission -->" in WORKFLOW.read_text(encoding="utf-8")
    assert "labels: [\"new-item\"]" in raw

    data = load_template(TEMPLATE)
    assert isinstance(data.get("body"), list)
    assert data.get("name")


def test_every_field_in_the_form_is_accounted_for() -> None:
    """Adding a field to the form must force a decision in the tool.

    Without this, a new input silently does nothing: it is rendered, filled in,
    and dropped on the floor because neither list mentions it — which is how the
    id came to be replaced by a generated one.
    """
    data = load_template(TEMPLATE)
    known = set(HEADER_FIELDS) | set(SECTION_FIELDS)
    # A checkbox is the gate, not data; markdown blocks carry no field.
    ignored = {"checkboxes", "markdown"}

    seen = set()
    for item in data["body"]:
        if not isinstance(item, dict) or item.get("type") in ignored:
            continue
        fid = item.get("id")
        assert fid, item
        seen.add(fid)
    assert seen == known, f"form fields with no home in the tool: {sorted(seen - known)}; " \
                          f"tool fields with no form input: {sorted(known - seen)}"

    # And every section heading the tool writes is a section the parser knows,
    # for a field the form actually has.
    for key, heading in SECTION_FIELDS.items():
        assert heading.startswith("## "), heading
        assert heading[3:].lower() in {s.lower() for s in INTAKE_SECTIONS}, heading
        assert key in seen, key


def test_the_form_labels_the_tool_reads_back_are_the_form_s_own() -> None:
    labels = field_labels(load_template(TEMPLATE))
    assert set(LABELS.values()) <= set(labels)
    for key, label in LABELS.items():
        assert labels.get(label) == key, (key, label, labels.get(label))


def test_parse_issue_reads_sections_not_just_lines() -> None:
    """A `### ` line inside a textarea must stay part of that textarea."""
    labels = field_labels(load_template(TEMPLATE))
    body = issue_body(prompt="请按下列要求作答：\n\n### 输出格式\n\n分三段。")
    parsed = parse_issue(body, labels)
    assert parsed["prompt"] == "请按下列要求作答：\n\n### 输出格式\n\n分三段。"
    assert parsed["task_type"] == DEFAULTS["task_type"]

    # `_No response_` is GitHub's "left blank", not the literal string.
    assert parse_issue(issue_body(), labels)["id"] == ""
    assert parse_issue(issue_body(), labels)["notes"] == ""


def test_the_intake_form_is_what_the_parser_expects() -> None:
    from acnlb.scaffold import parse_intake

    labels = field_labels(load_template(TEMPLATE))
    values = parse_issue(issue_body(documents="docs/a.md\ndocs/b.md", authority_basis="《民法典》第1条, 《公司法》第2条"), labels)
    text = to_intake(values, "core-tx-9001")

    parsed = parse_intake(text)
    assert parsed.meta["id"] == "core-tx-9001"
    assert parsed.meta["track"] == "core"
    assert parsed.documents == ["docs/a.md", "docs/b.md"]
    assert parsed.prompt and parsed.gold and parsed.notes is not None

    # A non-retrieval item must not carry an empty retrieval section: the parser
    # reads that section and refuses it for having no `class:`, so writing it
    # blank turns "not applicable" into an error.
    assert "## Retrieval gold" not in text

    # Header lines are single lines: a multi-line task must not become a section.
    assert one_line("a\nb") == "a b"


# ---------- the happy path ----------

def written(report: dict) -> list[str]:
    """`written` is reported relative to the repo root; compare it in those terms."""
    return sorted(p[len(report["items_dir"]) + 1:] for p in report["written"])


def test_a_submission_becomes_the_files_the_cli_writes(tmp_path: Path) -> None:
    report, out = run(tmp_path, issue_body(
        documents="  docs/core-tx-0003-loan.md  ",
        authority_basis="《民法典》第1条, 《公司法》第2条",
    ))

    assert report["ok"], report["errors"]
    # No id in the form: one is taken from the published set's own numbering.
    assert report["id"] == "core-tx-0003"
    assert written(report) == [
        "core-tx-0003.json", "core-tx-0003.rubric.md", "gold/core-tx-0003.md",
    ]
    assert report["items_dir"].endswith("items/incoming")
    for path in report["written"]:
        assert (ROOT / path).is_file(), path

    item = Item.load(out / "core-tx-0003.json")
    assert item.has_context is True, "has_context must follow the document list"
    assert [d.path for d in item.documents] == ["docs/core-tx-0003-loan.md"]
    assert item.authority_basis == ["《民法典》第1条", "《公司法》第2条"]
    assert item.category == "Transaction"
    assert item.gold_answer == "gold/core-tx-0003.md"

    # The rubric was left blank, so it is the skeleton — and a skeleton is a draft,
    # which is what makes the Action open the pull request as a draft.
    assert "TODO" in (out / "core-tx-0003.rubric.md").read_text(encoding="utf-8")
    assert any("TODO" in w for w in report["warnings"]), report["warnings"]


def test_a_typed_id_is_kept(tmp_path: Path) -> None:
    """The regression this test exists for: the id used to be overwritten."""
    report, out = run(tmp_path, issue_body(id="  core-lit-0042  "))
    assert report["id"] == "core-lit-0042"
    assert (out / "core-lit-0042.json").is_file()
    assert not (out / "core-lit-0006.json").exists(), "a generated id was written anyway"


def test_running_twice_proposes_the_same_id(tmp_path: Path) -> None:
    """Editing the issue must not move the item to a new id.

    The Action rebuilds the branch from the issue on every edit, so an id that
    depends on how many times the tool has run would give each edit its own branch
    and its own pull request. This is why the numbering reads the reference set
    rather than the scratch directory it has just written to.
    """
    body = issue_body()
    first, out = run(tmp_path, body)
    second, _ = run(tmp_path, body)
    assert first["id"] == second["id"] == "core-tx-0003"
    assert written(first) == written(second)
    assert not (out / "core-tx-0004.json").exists()


def test_the_numbering_follows_the_set_it_is_told_to(tmp_path: Path) -> None:
    """A maintainer pointing at a grown set gets ids numbered after it."""
    reference = tmp_path / "grown"
    reference.mkdir()
    (reference / "core-tx-0009.json").write_text(
        json.dumps({"id": "core-tx-0009", "track": "core", "category": "Transaction"}),
        encoding="utf-8",
    )
    from tools.issue_to_intake import set_vocab

    vocab = set_vocab(reference, tmp_path / "items/incoming")
    from acnlb.vocab import next_id

    assert next_id(vocab, track="core", category="Transaction") == "core-tx-0010"


def test_a_retrieval_submission_writes_its_gold(tmp_path: Path) -> None:
    body = issue_body(track="retrieval", category="Retrieval", task_type="法条检索",
                      retrieval_gold=GOLD)
    report, out = run(tmp_path, body)
    assert report["ok"], report["errors"]
    assert report["id"] == "ret-0011"

    item = Item.load(out / "ret-0011.json")
    assert item.retrieval_gold is not None
    assert item.retrieval_gold.klass == "statute"
    assert [(g.tier, g.ref) for g in item.retrieval_gold.gold_items] == [
        ("高", "《民法典》第585条"),
        ("中", "《民法典》第577条"),
    ]


def test_a_new_submission_numbers_like_the_published_set(tmp_path: Path) -> None:
    """The convention comes from the reference set, not from the empty target.

    A first item numbered `core-tx-1` while the published set uses `core-tx-0001`
    is a naming split nobody notices until a report sorts ids.
    """
    from acnlb.vocab import build_vocab, next_id

    reference = ROOT / REFERENCE_SET
    reference_raws = [json.loads(p.read_text(encoding="utf-8")) for p in sorted(reference.glob("*.json"))]
    assert next_id(build_vocab(reference_raws), track="core", category="Transaction") == "core-tx-0003"

    report, _ = run(tmp_path, issue_body())
    assert report["id"] == "core-tx-0003"
    assert len(report["id"]) == len("core-tx-0003")


# ---------- refusal ----------

@pytest.mark.parametrize("bad_id", ["../../etc/passwd", "/etc/passwd", "..", "a b", "id/nested"])
def test_a_bad_id_is_refused_before_anything_is_written(bad_id: str, tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="id"):
        run(tmp_path, issue_body(id=bad_id))


@pytest.mark.parametrize("bad_doc", ["../../etc/passwd", "/etc/passwd", "docs/../../x", "C:\\x.md"])
def test_a_document_path_that_escapes_is_refused(bad_doc: str, tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="document path"):
        run(tmp_path, issue_body(documents=bad_doc))


def test_a_retrieval_item_without_gold_says_what_is_missing(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Retrieval gold"):
        run(tmp_path, issue_body(track="retrieval", task_type="法条检索"))


def test_an_issue_that_is_not_the_form_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="表单|form field"):
        run(tmp_path, "这是一个普通的 issue。\n\n### 随便什么\n\n内容\n")


def test_an_oversized_body_is_refused(tmp_path: Path) -> None:
    with pytest.raises(ToolError, match="limit"):
        run(tmp_path, issue_body(notes="x" * (MAX_BODY + 1)))


def test_a_refused_submission_leaves_no_items_behind(tmp_path: Path) -> None:
    """The Action comments the error back; a half-written item would be worse."""
    for body in (issue_body(id="a b"), issue_body(documents="/etc/passwd")):
        with pytest.raises((ToolError, ValueError)):
            run(tmp_path, body)
    assert not list((tmp_path / "items").rglob("*.json")) if (tmp_path / "items").exists() else True


# ---------- the workflow reads what the tool writes ----------

def test_the_workflow_consumes_the_tool_s_report() -> None:
    raw = WORKFLOW.read_text(encoding="utf-8")
    # The id comes out of the JSON report, not out of the log.
    assert 'jq -r .id "$RUNNER_TEMP/item/report.json"' in raw
    assert "--report" in raw
    # The body reaches the tool as a file, never as an argument: it is text a
    # stranger typed, and a shell would interpret it.
    assert "ISSUE_BODY" in raw
    assert '"$RUNNER_TEMP/item/body.md"' in raw
    assert "--body \"$RUNNER_TEMP/item/body.md\"" in raw
    # Draft when validate fails, ready when it passes.
    assert "--draft" in raw
    assert "gh pr create" in raw
    assert "pull-requests: write" in raw
    # Nothing lands on the default branch.
    assert "git push --force-with-lease origin \"$BRANCH\"" in raw


def test_the_workflow_writes_where_the_tool_defaults() -> None:
    from tools.issue_to_intake import DEFAULT_OUT

    raw = WORKFLOW.read_text(encoding="utf-8")
    assert f"ITEM_SET: {DEFAULT_OUT}" in raw
