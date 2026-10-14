"""Parity between site/item-form.js and the Python it re-implements.

The web form is a second implementation of ``scaffold.py`` + ``rubric.py`` +
``Item.from_dict``. A second implementation is only acceptable if it can be
shown to agree, and "shown" has to mean executed: the failure mode is silent —
the form accepts an item the CLI refuses, and it is discovered in somebody
else's checkout at commit time. So these tests run both sides on the same input
and compare the output, including on the ten real rubrics.

Skipped when node is unavailable (the harness needs it); CI installs one.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb.schema import SchemaError  # noqa: E402
from acnlb.scaffold import parse_intake, scaffold  # noqa: E402
from acnlb.rubric import parse_rubric_text  # noqa: E402
from tools.build_site_schema import build as build_schema  # noqa: E402

NODE = shutil.which("node")
if NODE is None:
    for candidate in (
        "/Users/eeltamer/.workbuddy/binaries/node/versions/22.22.2-6/bin/node",
        "/usr/local/bin/node",
    ):
        if Path(candidate).exists():
            NODE = candidate
            break

requires_node = pytest.mark.skipif(NODE is None, reason="node not available")

HARNESS = ROOT / "tests" / "form_harness.js"
SCHEMA_PATH = ROOT / "site" / "schema.json"


def run_harness(op: str, payload: dict, tmp_path: Path) -> dict:
    payload_path = tmp_path / f"payload-{op}.json"
    payload_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    proc = subprocess.run(
        [NODE, str(HARNESS), op, str(payload_path)],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, f"harness {op} failed:\n{proc.stderr}"
    return json.loads(proc.stdout)


# ---------- fixtures ----------

CORE_MINIMAL = """id: core-tx-9001
track: core
category: Transaction
task_type: 合同审查与风险点识别
task: 识别增资协议中的重大风险条款
jurisdiction: CN-mainland
has_context: false
authority_basis: 《民法典》, 《公司法》(2023修订)
notes: SYNTHETIC — 合成示例

## Prompt

你是一家中国律师事务所的执业律师。请审阅随附材料并出具审查意见。
要求分「条款定位 + 风险 + 建议」三段式呈现。

## Documents

## Gold answer

（参考答案正文，第一段。）

## Rubric

"""

CORE_WITH_DOCS = """id: core-lit-9002
track: core
category: Litigation
task_type: 请求权基础分析
task: 就产品致害出具请求权基础分析
jurisdiction: CN-mainland
has_context: 有
authority_basis: 《民法典》第186条、第1203条; 《产品质量法》

## Prompt

请就下列事实出具请求权基础分析。

## Documents

- docs/core-lit-9002-facts.md
- docs/core-lit-9002-receipt.md

## Gold answer

一、合同路径。二、侵权路径。三、竞合处理。

## Rubric

# core-lit-9002 rubric — 请求权基础分析

## Affirmative Points

### 1. Structure (格式与结构)
- 1 pt  是否按「合同 / 侵权 / 竞合 / 策略」分层展开？

### 2. Style (风格)
- N/A

### 3. Substance (实质)
#### 3a. 基础分
- 1 pt  是否检验合同路径要件？
- 2.5 pts 是否准确表述§186 竞合择一规则？

## Negative Points
- -1 pt  [HALLUC_CITE] 编造条文
- -0.5 pt [EXTRATEXT] 无关冗余表述

## Notes

（合成示例。）
"""

RETRIEVAL_WITH_GOLD = """id: ret-9003
track: retrieval
category: Retrieval
task_type: 法条检索
task: 检索违约金司法调整规则的现行依据
jurisdiction: CN-mainland
has_context: false
authority_basis: 《民法典》第585条

## Prompt

请给出法律名称与条文序号，并摘录关键条文内容。

## Gold answer

《民法典》第585条。

## Rubric

# ret-9003 rubric — 违约金调减依据

## Affirmative Points

### 1. Structure (格式与结构)
- 1 pt  是否给出法律名称 + 条号？

## Negative Points
- -1 pt  [REPEALED_LAW] 引用《合同法》第114条

## Retrieval gold

class: statute

- 高 | 《民法典》第585条 | 违约金司法调减的现行直接依据
- 中 | 《民法典》第577条 | 违约责任一般规定
- 低 | （2021）最高法民申1号 | 说理可参照
"""

RETRIEVAL_NO_GOLD = """id: ret-9004
track: retrieval
task_type: 法条检索
task: 缺少检索基准
has_context: false

## Prompt

请检索。

## Gold answer

（参考答案。）
"""

RETRIEVAL_BAD_TIER = """id: ret-9005
track: retrieval
task_type: 法条检索
task: tier 非法
has_context: false

## Prompt

请检索。

## Gold answer

（参考答案。）

## Retrieval gold

class: statute

- 极高 | 《民法典》第585条 | 非法 tier
"""

HAS_CONTEXT_NO_DOCS = """id: core-tx-9006
track: core
task_type: 合同审查
task: 声明有附件却没列附件
has_context: true

## Prompt

请审查。

## Gold answer

（参考答案。）
"""

GOOD_FIXTURES = [CORE_MINIMAL, CORE_WITH_DOCS, RETRIEVAL_WITH_GOLD]
BAD_FIXTURES = [RETRIEVAL_NO_GOLD, RETRIEVAL_BAD_TIER, HAS_CONTEXT_NO_DOCS]
ALL_FIXTURES = GOOD_FIXTURES + BAD_FIXTURES


def python_scaffold(text: str, out_dir: Path) -> tuple[dict | None, str | None]:
    """Run the real scaffolder. Returns (files_by_name, None) or (None, error)."""
    intake_path = out_dir / "intake.md"
    out_dir.mkdir(parents=True, exist_ok=True)
    intake_path.write_text(text, encoding="utf-8")
    try:
        scaffold(intake_path, out_dir)
    except (ValueError, SchemaError) as exc:
        return None, str(exc)
    item_file = next(p for p in out_dir.glob("*.json"))
    return {
        item_file.name: item_file.read_text(encoding="utf-8"),
        item_file.stem + ".rubric.md": (out_dir / f"{item_file.stem}.rubric.md").read_text("utf-8"),
        f"gold/{item_file.stem}.md": (out_dir / "gold" / f"{item_file.stem}.md").read_text("utf-8"),
    }, None


@requires_node
@pytest.mark.parametrize("intake_text", GOOD_FIXTURES)
def test_form_writes_what_scaffold_writes(intake_text: str, tmp_path: Path) -> None:
    """Byte-equal for the markdown, key-for-key equal for the JSON.

    The item JSON is compared as parsed objects plus key order rather than as
    bytes: Python serialises 5.0 and JavaScript serialises 5 for the same float,
    and rewriting JS's number formatting to match would be a formatting
    coincidence dressed up as a correctness guarantee.
    """
    py_files, py_err = python_scaffold(intake_text, tmp_path / "py")
    assert py_err is None, f"python rejected a fixture it should accept: {py_err}"

    js = run_harness("build", {"intake": intake_text}, tmp_path)
    assert js["ok"], f"js rejected a fixture python accepts: {js['errors']}"

    js_files = {f["name"]: f["data"] for f in js["files"]}
    assert sorted(js_files) == sorted(py_files)

    for name in sorted(py_files):
        if name.endswith(".json"):
            py_obj = json.loads(py_files[name])
            js_obj = json.loads(js_files[name])
            assert list(py_obj) == list(js_obj), f"{name}: key order differs"
            assert py_obj == js_obj, f"{name}: value differs"
        else:
            assert js_files[name] == py_files[name], f"{name}: text differs"

    # The common failure that motivated the whole parity test: a form-produced
    # item must survive the CLI's own loader.
    from acnlb.schema import Item

    Item.from_dict(json.loads(js_files[next(n for n in js_files if n.endswith(".json"))]))


@requires_node
@pytest.mark.parametrize("intake_text", BAD_FIXTURES)
def test_both_sides_reject_the_same_inputs(intake_text: str, tmp_path: Path) -> None:
    """Anything `validate` would refuse must be refused in the browser too.

    A form that fails open is worse than no form: the drafter gets files that
    look right, and the error surfaces at commit time in a checkout they may not
    even have.
    """
    py_files, py_err = python_scaffold(intake_text, tmp_path / "py")
    assert py_files is None, "python accepted a fixture it should reject"
    assert py_err

    js = run_harness("build", {"intake": intake_text}, tmp_path)
    assert not js["ok"], "js accepted input python rejects"
    assert js["errors"], "js rejected without saying why"


@requires_node
@pytest.mark.parametrize("rubric_path", sorted((ROOT / "items" / "bench10").glob("*.rubric.md")),
                         ids=lambda p: p.stem)
def test_rubric_parser_matches_on_the_real_rubrics(rubric_path: Path, tmp_path: Path) -> None:
    """The ten shipped rubrics, both parsers, field by field.

    max_positive_points is what the item JSON stores and what the score is a
    fraction of, so a parser that drops one line reads as a lower ceiling, not as
    an error.
    """
    text = rubric_path.read_text(encoding="utf-8")
    py = parse_rubric_text(text)
    js = run_harness("rubric", {"text": text}, tmp_path)

    assert js["itemId"] == py.item_id
    assert js["title"] == py.title
    assert [a["points"] for a in js["affirmative"]] == [a.points for a in py.affirmative]
    assert [a["text"] for a in js["affirmative"]] == [a.text for a in py.affirmative]
    assert [(a["section"], a["subsection"]) for a in js["affirmative"]] == \
           [(a.section, a.subsection) for a in py.affirmative]
    assert [n["code"] for n in js["negative"]] == [n.code for n in py.negative]
    assert [n["points"] for n in js["negative"]] == [n.points for n in py.negative]
    assert [n["text"] for n in js["negative"]] == [n.text for n in py.negative]
    assert js["maxPositivePoints"] == py.max_positive_points
    assert js["warnings"] == py.warnings


@requires_node
def test_draft_lint_matches_validate(tmp_path: Path) -> None:
    """A form filled in with no rubric gets the skeleton, and the skeleton is a draft.

    `acnlb validate` rejects a TODO placeholder; the form cannot reject it (the
    drafter is mid-thought), so it must at least say so — otherwise an item that
    validate will refuse looks finished on the page.
    """
    from acnlb.scaffold import DEFAULT_RUBRIC

    assert "TODO" in DEFAULT_RUBRIC

    js = run_harness("build", {"intake": CORE_MINIMAL}, tmp_path)
    assert js["ok"], js["errors"]
    assert any("TODO" in w for w in js["lint"]), js["lint"]
    assert any("参考答案" in w for w in js["lint"]) is False  # gold is supplied here

    no_gold = CORE_MINIMAL.split("## Gold answer")[0] + "## Gold answer\n\n（留空。）\n"
    js2 = run_harness("build", {"intake": no_gold}, tmp_path)
    assert js2["ok"], js2["errors"]
    assert js2["id"] == "core-tx-9001"


@requires_node
def test_row_roundtrip_is_stable(tmp_path: Path) -> None:
    """row → intake → row must be a fixed point, or batch export loses fields.

    Compared modulo trailing whitespace: an intake section body is stripped on
    the way in, so a textarea value ending in a newline comes back without it.
    That is the format's behaviour, not drift, and the export adds the newline
    back where a file needs one.
    """
    row = {
        "id": "wf-9007", "track": "workflows", "category": "Workflow",
        "task_type": "要素抽取", "task": "抽取要素为 JSON",
        "jurisdiction": "CN-mainland", "has_context": False,
        "authority_basis_text": "《民法典》, 《公司法》", "notes": "SYNTHETIC",
        "prompt": "请抽取要素。", "documents": [],
        "gold": '{"a": 1}', "rubric": "## Affirmative Points\n\n- 1 pt  是否输出合法 JSON？\n",
        "retrieval_class": "", "retrieval_items": [],
    }
    out = run_harness("roundtrip", {"row": row}, tmp_path)
    assert out["errors"] == []

    def norm(d: dict) -> dict:
        return {k: (v.rstrip() if isinstance(v, str) else v) for k, v in d.items()}

    assert norm(out["rebuilt"]) == norm(row)
    assert out["rebuilt"]["authority_basis_text"] == "《民法典》, 《公司法》"


@requires_node
def test_bulk_split_reads_back_to_back_forms(tmp_path: Path) -> None:
    """Pasting several forms is the batch path.

    Splitting is by a top-level `id:` line or an explicit `%%%` line. What
    matters is that the split agrees with the CLI, which parses one form at a
    time — so each block it produces is fed to the real scaffolder.
    """
    blob = "%%%\n".join(GOOD_FIXTURES)
    script = (
        "const f=require(process.argv[1]);"
        "process.stdout.write(JSON.stringify(f.splitIntakes(process.argv[2])));"
    )
    proc = subprocess.run(
        [NODE, "-e", script, str(ROOT / "site" / "item-form.js"), blob],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc.returncode == 0, proc.stderr
    blocks = json.loads(proc.stdout)
    assert len(blocks) == len(GOOD_FIXTURES)

    for i, block in enumerate(blocks):
        py_files, py_err = python_scaffold(block, tmp_path / f"py{i}")
        assert py_err is None, f"block {i} does not survive the CLI: {py_err}"
        js = run_harness("build", {"intake": block}, tmp_path)
        assert js["ok"], f"block {i} rejected in js: {js['errors']}"

    # `id:` at column 0 is the other separator, and must not fire on the first line.
    script2 = (
        "const f=require(process.argv[1]);"
        "process.stdout.write(String(f.splitIntakes(process.argv[2]).length));"
    )
    proc2 = subprocess.run(
        [NODE, "-e", script2, str(ROOT / "site" / "item-form.js"),
         CORE_MINIMAL + RETRIEVAL_WITH_GOLD],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert proc2.returncode == 0, proc2.stderr
    assert proc2.stdout.strip() == "2"


@requires_node
def test_js_zip_is_a_real_zip(tmp_path: Path) -> None:
    """The batch export builds a zip in the browser; Python must be able to open it.

    Store-only and hand-rolled, so the load-bearing question is not "does it look
    like a zip" but "does the reference implementation accept it and return the
    bytes we put in".
    """
    entries = [
        {"name": "core-tx-9001.json", "data": "{\"id\": \"core-tx-9001\"}\n"},
        {"name": "core-tx-9001.rubric.md", "data": "# 中文 rubric\n- 1 pt  是否？\n"},
        {"name": "gold/core-tx-9001.md", "data": "参考答案\n"},
    ]
    out_path = tmp_path / "js.zip"
    res = run_harness("zip", {"entries": entries, "out": str(out_path)}, tmp_path)

    with zipfile.ZipFile(out_path) as zf:
        assert zf.testzip() is None
        assert zf.namelist() == [e["name"] for e in entries]
        for e in entries:
            assert zf.read(e["name"]).decode("utf-8") == e["data"]
    assert res["bytes"] == out_path.stat().st_size


def test_site_schema_is_in_sync(tmp_path: Path) -> None:
    """site/schema.json is what the form trusts; it must be the package's own words."""
    assert SCHEMA_PATH.is_file(), "run: python tools/build_site_schema.py"
    committed = json.loads(SCHEMA_PATH.read_text(encoding="utf-8"))
    assert committed == build_schema()

    # Spot-check the constants that actually gate acceptance in the browser.
    from acnlb import negatives
    from acnlb.schema import VALID_TRACKS

    assert set(committed["valid_tracks"]) == set(VALID_TRACKS)
    assert {n["code"] for n in committed["negatives"]} == set(negatives.CODES)
    assert "TODO" in committed["default_rubric"]


# ---------- the two rules that turn a string into a path ----------

# Chosen so both sides have to agree on the *rule*, not on the wording: the page
# prints its own sentence (it is bilingual), Python prints one.
PATH_CASES = [
    "core-tx-0003", "ret-0011", "x", "core_tx.1", "A-b_c.d",
    "", "   ", ".", "..", "/etc/passwd", "\\etc\\passwd", "C:\\x.md",
    "a b", "a/b", "core tx", "…", "../x", "docs/../x", "x.json",
    "docs/core-tx-0001-loan-guarantee.md", "docs//a.md", "gold/a.md",
    "-flag", "id\n", "\tshift",
]


@requires_node
def test_id_rules_agree_with_the_cli(tmp_path: Path) -> None:
    from acnlb.schema import id_problem

    js = run_harness("rules", {"values": PATH_CASES}, tmp_path)
    assert [c["value"] for c in js["ids"]] == PATH_CASES
    for case in js["ids"]:
        py = id_problem(case["value"])
        assert bool(py) == bool(case["problem"]), (
            f"id {case['value']!r}: python says {py!r}, js says {case['problem']!r}"
        )


@requires_node
def test_document_path_rules_agree_with_the_cli(tmp_path: Path) -> None:
    from acnlb.schema import doc_path_problem

    js = run_harness("rules", {"values": PATH_CASES}, tmp_path)
    for case in js["docs"]:
        py = doc_path_problem(case["value"])
        assert bool(py) == bool(case["problem"]), (
            f"document path {case['value']!r}: python says {py!r}, js says {case['problem']!r}"
        )


@requires_node
def test_the_form_refuses_the_paths_the_cli_refuses(tmp_path: Path) -> None:
    """The load-bearing half: a bad path must not survive `buildItem`.

    Checking `docPathProblem` on its own proves the two functions agree; it does
    not prove the form calls them. This is the failure the whole constraint exists
    for — an item that looks fine on the page and is refused at commit time.
    """
    bad_id = CORE_MINIMAL.replace("id: core-tx-9001", "id: ../../escape")
    js = run_harness("build", {"intake": bad_id}, tmp_path)
    assert not js["ok"] and js["errors"]

    intake = tmp_path / "in.md"
    bad_doc = CORE_WITH_DOCS.replace("docs/core-lit-9002-facts.md", "../../../etc/passwd")
    intake.write_text(bad_doc, encoding="utf-8")
    with pytest.raises(ValueError):
        scaffold(intake, tmp_path / "items")

    js2 = run_harness("build", {"intake": bad_doc}, tmp_path)
    assert not js2["ok"], "the form exported an item the CLI refuses"
    assert any("escapes" in e or "document path" in e for e in js2["errors"]), js2["errors"]


# ---------- the next free id ----------

def bench_vocab() -> dict:
    from acnlb.vocab import build_vocab

    raws = [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted((ROOT / "items" / "bench10").glob("*.json"))
    ]
    return build_vocab(raws)


NEXT_ID_CASES = [
    {},
    {"prefix": "core-tx-"},
    {"prefix": "wf-"},
    {"prefix": "nope-"},
    {"track": "core"},
    {"track": "retrieval"},
    {"track": "workflows"},
    {"track": "core", "category": "Transaction"},
    {"track": "core", "category": "Litigation"},
    {"track": "retrieval", "category": "Retrieval"},
    {"track": "core", "category": "Nonexistent"},
    {"track": "nope"},
    {"category": "Litigation"},
]


@requires_node
def test_next_id_agrees_with_the_cli(tmp_path: Path) -> None:
    """The page's "next free id" button and the issue tool must not disagree.

    They answer the same question about the same set, and an answer that is one
    off is an id that collides with an existing item — which `validate` cannot
    see, because the file it would collide with is already there under the same
    name.
    """
    from acnlb.vocab import next_id

    vocab = bench_vocab()
    js = run_harness("nextid", {"vocab": vocab, "cases": NEXT_ID_CASES}, tmp_path)
    for case, got in zip(NEXT_ID_CASES, js["ids"]):
        assert got == next_id(vocab, **case), f"{case}: python {next_id(vocab, **case)!r}, js {got!r}"


# ---------- the rubric row editor ----------

def real_rubrics() -> list[Path]:
    return sorted((ROOT / "items" / "bench10").glob("*.rubric.md"))


@requires_node
@pytest.mark.parametrize("rubric_path", real_rubrics(), ids=lambda p: p.stem)
def test_rubric_rows_reproduce_the_rubric(rubric_path: Path, tmp_path: Path) -> None:
    """Editing a rubric as a table must not lose or reword a point.

    The editor's rows are the only representation of the rubric while it is open,
    so anything they cannot carry is a line the drafter sees and the export does
    not have. Comparing the *parsed* rubrics rather than the text is deliberate:
    the serialiser is allowed to normalise whitespace, and it is not allowed to
    change a section, a subsection, a score or a proposition.
    """
    text = rubric_path.read_text(encoding="utf-8")

    rows = run_harness("rowsfrom", {"text": text}, tmp_path)
    assert not rows["blocked"], rows["blocked"]

    back = run_harness(
        "rowsto",
        {"rows": rows["rows"], "id": rubric_path.stem, "task": "t"},
        tmp_path,
    )["text"]

    py = parse_rubric_text(text)
    again = parse_rubric_text(back)
    assert again.warnings == [], again.warnings
    assert [(a.section, a.subsection, a.points, a.text) for a in again.affirmative] == \
           [(a.section, a.subsection, a.points, a.text) for a in py.affirmative]
    assert [(n.code, n.points, n.text) for n in again.negative] == \
           [(n.code, n.points, n.text) for n in py.negative]
    assert again.max_positive_points == py.max_positive_points

    # And the rewritten rubric is still readable by the JS parser the page uses.
    js = run_harness("rubric", {"text": back}, tmp_path)
    assert js["maxPositivePoints"] == py.max_positive_points
    assert js["warnings"] == []


@requires_node
def test_rubric_rows_refuse_what_they_cannot_carry(tmp_path: Path) -> None:
    """An unrepresentable rubric goes to the raw editor rather than being trimmed."""
    from acnlb.scaffold import RUBRIC_LAYOUT

    # A heading outside the three the format defines: parsing it is fine, but the
    # row model has nowhere to put it, so writing rows back would drop the line.
    stray = "# x-1 rubric — t\n\n## Affirmative Points\n\n### 4. Bonus\n- 1 pt  加分项\n"
    rows = run_harness("rowsfrom", {"text": stray}, tmp_path)
    assert rows["blocked"], rows

    # A negative code outside the closed taxonomy: `validate` rejects it, and the
    # editor's code select could not offer it.
    unknown = ("# x-1 rubric — t\n\n## Affirmative Points\n\n### 1. Structure (格式与结构)\n"
               "- 1 pt  ok\n\n## Negative Points\n- -1 pt  [MADE_UP] nope\n")
    rows2 = run_harness("rowsfrom", {"text": unknown}, tmp_path)
    assert any("MADE_UP" in b for b in rows2["blocked"]), rows2["blocked"]

    # An empty rubric is not blocked: it is the state you start from, and the
    # editor has to be able to take the first point.
    empty = run_harness("rowsfrom", {"text": ""}, tmp_path)
    assert not empty["blocked"], empty
    assert empty["rows"] == []

    assert RUBRIC_LAYOUT["na"] == "- N/A"


@requires_node
def test_the_row_editor_writes_the_rubric_it_was_given(tmp_path: Path) -> None:
    """rows -> markdown -> rows is a fixed point, headings included."""
    from acnlb.scaffold import RUBRIC_LAYOUT

    rows = [
        {"kind": "affirmative", "section": "structure", "subsection": "", "points": 1, "text": "分层呈现"},
        {"kind": "affirmative", "section": "substance", "subsection": "3a. 优先购买权", "points": 2, "text": "放弃程序"},
        {"kind": "affirmative", "section": "substance", "subsection": "3a. 优先购买权", "points": 0.5, "text": "通知义务"},
        {"kind": "negative", "code": "REPEALED_LAW", "points": 1, "text": "引用已废止法律"},
    ]
    text = run_harness("rowsto", {"rows": rows, "id": "core-tx-9001", "task": "审查"}, tmp_path)["text"]
    assert text.startswith("# core-tx-9001 rubric — 审查\n")
    assert RUBRIC_LAYOUT["na"] in text, "an empty section must still be written as N/A"
    assert f"{RUBRIC_LAYOUT['heading_level']} 2. Style (风格)" in text

    back = run_harness("rowsfrom", {"text": text}, tmp_path)
    assert not back["blocked"], back["blocked"]
    assert back["rows"] == rows

    py = parse_rubric_text(text)
    assert py.item_id == "core-tx-9001"
    assert py.max_positive_points == 3.5
    assert [n.code for n in py.negative] == ["REPEALED_LAW"]


@requires_node
@pytest.mark.parametrize("track", ["core", "workflows", "retrieval"])
def test_the_page_can_edit_every_template_it_offers(track: str, tmp_path: Path) -> None:
    """A template the row editor cannot reopen is a dead end for the drafter.

    It is offered as a starting point, so it has to survive the round trip like
    any rubric: parsed by Python, and editable as rows.
    """
    from acnlb.scaffold import DEFAULT_RUBRIC, rubric_template

    # The page's copy of the track's skeleton must be the package's, verbatim.
    packed = rubric_template(track).replace("{item_id}", "core-tx-9001").replace("{task}", "审查")
    from_page = run_harness("template", {"track": track, "id": "core-tx-9001", "task": "审查"}, tmp_path)
    assert from_page["text"] == packed, f"{track}: the page's template differs from the package's"

    for tpl in (packed, DEFAULT_RUBRIC):
        text = tpl.replace("{item_id}", "core-tx-9001").replace("{task}", "审查")
        py = parse_rubric_text(text)
        assert py.affirmative, track
        assert py.warnings == [], (track, py.warnings)
        assert "TODO" in text

        rows = run_harness("rowsfrom", {"text": text}, tmp_path)
        assert not rows["blocked"], (track, rows["blocked"])
