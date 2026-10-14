"""Scaffold item directories from a plain-text intake form.

Authoring an item needs a task, a prompt, documents, a gold answer, and a rubric
(design doc §3.3-§3.4, §3.6). Only the last two cost real lawyer time; the rest is
metadata and file plumbing. This module turns a filled-in intake form into a
correctly-shaped item directory, so a drafter never hand-writes JSON.

Usage:  python -m acnlb new --intake <form.md> --out items/real
See `items/INTAKE.template.md` for the form.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .rubric import parse_rubric_text
from .schema import DEFAULT_TIER_POINTS, VALID_TIERS, Item, doc_path_problem

_SECTION = re.compile(r"^##\s+(.+?)\s*$")
_HEADER_LINE = re.compile(r"^([A-Za-z_][A-Za-z0-9_ ]*?)\s*[:：]\s*(.*)$")

# Section headings the parser understands (case-insensitive).
_GOLD = ("gold answer", "gold", "参考答案")
_RETRIEVAL = ("retrieval gold", "retrieval_gold", "检索 gold", "检索基准")
_KNOWN = {"prompt", "documents", "rubric", "notes"} | set(_GOLD) | set(_RETRIEVAL)

# Public view of the parser vocabulary. Exported so the web form can offer
# exactly the headings `parse_intake` understands instead of re-typing them.
INTAKE_SECTIONS: tuple[str, ...] = tuple(sorted(_KNOWN))
GOLD_SECTIONS: tuple[str, ...] = _GOLD
RETRIEVAL_SECTIONS: tuple[str, ...] = _RETRIEVAL

# Skeleton rubric: §3.4 headings, one Style=N/A section, and the FULL closed
# negative taxonomy pre-filled so a drafter picks from the allowed vocabulary
# rather than inventing codes. Affirmative lines carry TODO — `validate` rejects
# them until a real proposition replaces them.
DEFAULT_RUBRIC = """# {item_id} rubric — {task}

## Affirmative Points

### 1. Structure (格式与结构)
- 1 pt  TODO：格式或结构要求，例如「是否按「风险等级」或「条款类型」分层呈现？」

### 2. Style (风格)
- N/A

### 3. Substance (实质)
- 1 pt  TODO：一个可核验的实质命题，例如「是否指出需完成其他股东优先购买权放弃程序？【《公司法》第71条】」

## Negative Points
- -1 pt  [HALLUC_FACT] 编造文件/合同里不存在的事实、条款或数字
- -1 pt  [HALLUC_CITE] 编造不存在的法条、案号、司法解释
- -1 pt  [REPEALED_LAW] 引用已废止法律（如《合同法》《担保法》）或旧版本条文
- -1 pt  [WRONG_HIERARCHY] 把非约束性来源当约束性（参考性案例当指导性案例、地方文件当司法解释）
- -0.5 pt [EXTRATEXT] 准确但无关或错误引申的冗余表述
- -2 pts [FORMAT_BREACH] 未满足明确格式要求（长度下限、必含小节）——如不适用请删除本行
"""

# Per-track rubric templates (design doc §3.4, §3.6). DEFAULT_RUBRIC is the
# generic skeleton; these are the same skeleton shaped for what each track is
# graded on, so a drafter who picks the right one does not have to invent the
# Structure / Style / Substance split from scratch. Every affirmative line
# carries TODO, for the same reason DEFAULT_RUBRIC does: a template is a draft,
# and `validate` has to keep refusing it until somebody replaces the prose.
RUBRIC_TEMPLATES: dict[str, str] = {
    "core": """# {item_id} rubric — {task}

## Affirmative Points

### 1. Structure (格式与结构)
- 1 pt  TODO：输出形态，例如「是否按『条款定位 → 风险 → 建议』三段式呈现？」

### 2. Style (风格)
- 1 pt  TODO：语体与呈现要求，例如「是否以条款清单形式枚举，每条不超过 20 字？」

### 3. Substance (实质)
#### 3a. 核心命题
- 2 pts TODO：一个可核验的实质命题，例如「是否指出需完成其他股东优先购买权放弃程序？【《公司法》第71条】」
- 1 pt  TODO：第二个可核验命题

## Negative Points
- -1 pt  [HALLUC_FACT] 编造文件/合同里不存在的事实、条款或数字
- -1 pt  [HALLUC_CITE] 编造不存在的法条、案号、司法解释
- -1 pt  [REPEALED_LAW] 引用已废止法律（如《合同法》《担保法》）或旧版本条文
- -0.5 pt [EXTRATEXT] 准确但无关或错误引申的冗余表述
""",
    "workflows": """# {item_id} rubric — {task}

## Affirmative Points

### 1. Structure (格式与结构)
- 2 pts TODO：输出形态，例如「是否严格输出 JSON，且能被 json.loads 解析？」

### 2. Style (风格)
- 1 pt  TODO：字段与取值要求，例如「键名是否与模板完全一致？」

### 3. Substance (实质)
#### 3a. 字段正确性
- 1 pt  TODO：逐字段的可核验命题，例如「party_a 是否取到合同首部的甲方全称？」

## Negative Points
- -1 pt  [HALLUC_FACT] 编造文件里不存在的字段值
- -0.5 pt [EXTRATEXT] 输出形态之外的多余解释
- -2 pts [FORMAT_BREACH] 输出不是要求的固定形态（缺字段、多余包裹文本）——如不适用请删除本行
""",
    "retrieval": """# {item_id} rubric — {task}

## Affirmative Points

### 1. Structure (格式与结构)
- 1 pt  TODO：是否给出法律名称 + 条号（或案号 + 法院）？

### 2. Style (风格)
- 1 pt  TODO：是否按效力层级分组呈现？

### 3. Substance (实质)
#### 3a. 依据与分级
- 2 pts TODO：与「检索基准」逐条对应的可核验命题，例如「是否命中《民法典》第585条？」

## Negative Points
- -1 pt  [REPEALED_LAW] 引用已废止法律（如《合同法》第114条）
- -1 pt  [HALLUC_CITE] 编造不存在的法条、案号
- -1 pt  [WRONG_HIERARCHY] 把参考性案例当指导性案例、地方性文件当司法解释
""",
}


def rubric_template(track: str) -> str:
    """The skeleton for ``track``, falling back to the generic one.

    An unrecognised track is not an error here: `validate` rejects the track
    itself, and refusing to hand back a skeleton would only turn one clear
    message into two.
    """
    return RUBRIC_TEMPLATES.get(track, DEFAULT_RUBRIC)


def render_rubric_skeleton(track: str, item_id: str, task: str) -> str:
    """The skeleton for ``track`` with this item's id and task filled in.

    Both routes that create an item use this — `acnlb new` and the web form — so
    the same submission gets the same draft whichever way it was made. The form
    does the substitution in JavaScript from the exported templates; this is the
    same operation on one string.
    """
    return rubric_template(track).replace("{item_id}", item_id).replace("{task}", task)


# The rubric format's own vocabulary, as data rather than as format strings
# sprinkled through the writers. The web form edits a rubric as a table of rows,
# which means it has to *emit* markdown — and a second set of headings typed into
# JavaScript is exactly how the two parse differently. So the headings, the level
# markers and the line shapes live here; the form reads them from `schema.json`
# and `tests/test_site_contract.py` fails if a heading appears in the JS at all.
RUBRIC_LAYOUT: dict[str, Any] = {
    "title": "# {item_id} rubric — {task}",
    "affirmative_heading": "## Affirmative Points",
    "negative_heading": "## Negative Points",
    # Ordered: the form offers them in this order, and the order is the numbering
    # in the heading text.
    "sections": [
        {"key": "structure", "title": "1. Structure (格式与结构)", "section": "Structure"},
        {"key": "style", "title": "2. Style (风格)", "section": "Style"},
        {"key": "substance", "title": "3. Substance (实质)", "section": "Substance"},
    ],
    "heading_level": "###",
    "subsection_level": "####",
    "affirmative_item": "- {points} {unit}  {text}",
    "negative_item": "- -{points} {unit}  [{code}] {text}",
    # A section with no points of its own. `parse_rubric_text` reads it as "no
    # points here" rather than as an unparsed line, which is what keeps a
    # round trip through the form from inventing a warning.
    "na": "- N/A",
    "points": {"one": "pt", "many": "pts"},
}


@dataclass
class Intake:
    meta: dict[str, str] = field(default_factory=dict)
    prompt: str = ""
    documents: list[str] = field(default_factory=list)
    gold: str = ""
    rubric: str = ""
    notes: str = ""
    # retrieval items only: (class, [(tier, ref, note), ...]). Parsed here rather
    # than hand-edited into the generated JSON afterwards — a gold block added by
    # hand is a block `validate` cannot check until it is already committed.
    retrieval_gold: tuple[str, list[tuple[str, str, str]]] | None = None


def parse_gold_block(block: str) -> tuple[str, list[tuple[str, str, str]]]:
    """Parse a ``## Retrieval gold`` body into ``(class, [(tier, ref, note)])``.

    Body shape::

        class: statute

        - 高 | 《民法典》第585条 | 违约金司法调减的现行直接依据
        - 中 | ...                  | ...
    """
    klass = ""
    items: list[tuple[str, str, str]] = []
    for raw in block.splitlines():
        line = raw.strip()
        if not line:
            continue
        hm = _HEADER_LINE.match(line)
        if hm and hm.group(1).strip().lower().replace(" ", "_") == "class":
            klass = hm.group(2).strip()
            continue
        if not line.startswith(("-", "*")):
            continue
        parts = [p.strip() for p in line.lstrip("-*").split("|")]
        if len(parts) < 2:
            raise ValueError(
                f"retrieval gold line needs '<tier> | <ref> | <note>': {line!r}"
            )
        tier, ref = parts[0], parts[1]
        note = parts[2] if len(parts) > 2 else ""
        if tier not in VALID_TIERS:
            raise ValueError(
                f"invalid tier {tier!r} in retrieval gold; use one of {sorted(VALID_TIERS)}"
            )
        if not ref:
            raise ValueError(f"retrieval gold line has no ref: {line!r}")
        items.append((tier, ref, note))
    if not klass:
        raise ValueError("retrieval gold section is missing 'class:'")
    return klass, items


def parse_intake(text: str) -> Intake:
    """Parse an intake form. Header is ``key: value`` lines; then ``## Section`` blocks."""
    intake = Intake()
    section: str | None = None
    buf: list[str] = []

    def flush() -> None:
        nonlocal buf, section
        if section is not None:
            block = "\n".join(buf).strip("\n")
            if section == "prompt":
                intake.prompt = block.strip()
            elif section == "documents":
                intake.documents = _parse_list(block)
            elif section in _GOLD:
                intake.gold = block.strip()
            elif section == "rubric":
                intake.rubric = block.strip()
            elif section == "notes":
                intake.notes = block.strip()
            elif section in _RETRIEVAL:
                intake.retrieval_gold = parse_gold_block(block)
        buf = []

    for raw in text.splitlines():
        line = raw.rstrip()
        m = _SECTION.match(line)
        if m and m.group(1).strip().lower() in _KNOWN:
            flush()
            section = m.group(1).strip().lower()
            continue
        if section is None:
            if not line.strip() or line.lstrip().startswith("#"):
                continue
            hm = _HEADER_LINE.match(line.strip())
            if hm:
                key = hm.group(1).strip().lower().replace(" ", "_")
                intake.meta[key] = hm.group(2).strip()
            continue
        buf.append(line)
    flush()
    return intake


def _parse_list(block: str) -> list[str]:
    out = []
    for line in block.splitlines():
        s = line.strip().lstrip("-*").strip()
        if s and not s.startswith("#"):
            out.append(s)
    return out


def _split_basis(value: str) -> list[str]:
    return [p.strip() for p in re.split(r"[,，、;；]", value or "") if p.strip()]


def _as_bool(value: str) -> bool:
    v = str(value).strip().lower()
    if v in ("true", "yes", "y", "1", "是", "有", "有附件"):
        return True
    if v in ("false", "no", "n", "0", "否", "无", "无附件"):
        return False
    raise ValueError(f"has_context must be true/false, got {value!r}")


def scaffold(
    intake_path: str | Path,
    out_dir: str | Path,
    *,
    item_id: str | None = None,
    force: bool = False,
) -> tuple[list[Path], list[str]]:
    """Write ``<id>.json`` + ``gold/<id>.md`` + ``<id>.rubric.md``. Returns (paths, warnings)."""
    intake = parse_intake(Path(intake_path).read_text(encoding="utf-8"))
    meta = intake.meta

    iid = item_id or meta.get("id", "")
    if not iid:
        raise ValueError("intake is missing 'id'")
    missing = [k for k in ("track", "task_type", "task") if not meta.get(k)]
    if missing:
        raise ValueError(f"intake is missing required field(s): {', '.join(missing)}")
    if not intake.prompt.strip():
        raise ValueError("intake is missing a '## Prompt' section")
    # Document paths are stored in the item and resolved against the items
    # directory, so they have to stay inside it. Checked before anything is
    # written: the path is usually something a stranger typed into a form, and a
    # `../..` that lands in a commit is not something `validate` can undo.
    for doc in intake.documents:
        problem = doc_path_problem(doc)
        if problem:
            raise ValueError(problem)

    task = meta["task"]
    notes = (meta.get("notes", "") + ("\n" + intake.notes if intake.notes else "")).strip()

    # Rubric first, so max_positive_points is derived from the real text.
    rubric_text = intake.rubric or render_rubric_skeleton(meta["track"], iid, task)
    rubric = parse_rubric_text(rubric_text)

    has_ctx = _as_bool(meta["has_context"]) if meta.get("has_context") else bool(intake.documents)

    warnings: list[str] = []
    if intake.retrieval_gold is not None and meta["track"] != "retrieval":
        # The intake template carries this section so the form/CLI has one shape
        # for both tracks. Dropping it loudly beats either writing an item that
        # `validate` refuses, or failing on a template copied as documented.
        warnings.append(
            "'## Retrieval gold' section ignored: it only applies to track=retrieval"
        )

    if meta["track"] == "retrieval" and intake.retrieval_gold is None:
        # Fail here with a message that names the fix. Letting Item.from_dict
        # raise instead would print "must carry a retrieval_gold block" and send
        # the drafter hunting for a JSON key the intake format never mentions.
        raise ValueError(
            "retrieval items need a '## Retrieval gold' section "
            "(a 'class:' line plus '- <tier> | <ref> | <note>' lines)"
        )

    rubric_rel = f"{iid}.rubric.md"
    gold_rel = f"gold/{iid}.md"
    data = {
        "id": iid,
        "track": meta["track"],
        "category": meta.get("category", ""),
        "task_type": meta["task_type"],
        "task": task,
        "prompt": intake.prompt.strip(),
        "documents": [{"path": p} for p in intake.documents],
        "has_context": has_ctx,
        "jurisdiction": meta.get("jurisdiction", "CN-mainland"),
        "authority_basis": _split_basis(meta.get("authority_basis", "")),
        "gold_answer": gold_rel,
        "rubric": rubric_rel,
        "max_positive_points": rubric.max_positive_points,
        "notes": notes,
    }
    if intake.retrieval_gold is not None and meta["track"] == "retrieval":
        klass, gold_rows = intake.retrieval_gold
        data["retrieval_gold"] = {
            "class": klass,
            "gold_items": [
                {"ref": ref, "tier": tier, "note": note} for tier, ref, note in gold_rows
            ],
            "tier_points": dict(DEFAULT_TIER_POINTS),
        }

    # Shape-check before writing anything: a bad form fails here, not at run time.
    Item.from_dict(data)

    out = Path(out_dir)
    (out / "gold").mkdir(parents=True, exist_ok=True)
    (out / "docs").mkdir(parents=True, exist_ok=True)

    written: list[Path] = []

    def write(p: Path, text: str) -> None:
        if p.exists() and not force:
            raise FileExistsError(f"{p} already exists (pass --force to overwrite)")
        p.write_text(text, encoding="utf-8")
        written.append(p)

    gold_text = intake.gold or (
        f"# {iid} 参考答案\n\n"
        "<!-- TODO：先写「一名胜任律师会产出的回答」，再据此写 rubric（设计文档 §3.6）。\n"
        "     顺序不能反——先写 rubric 会锚定在你想到的东西上，参考答案就不完整。 -->\n"
    )

    write(out / gold_rel, gold_text)
    write(out / rubric_rel, rubric_text if rubric_text.endswith("\n") else rubric_text + "\n")
    write(out / f"{iid}.json", json.dumps(data, ensure_ascii=False, indent=2) + "\n")

    for doc in intake.documents:
        if not (out / doc).exists():
            warnings.append(f"document not found yet: {doc} (put it under {out}/)")
    if "TODO" in rubric_text:
        warnings.append("rubric still contains TODO placeholders — `validate` will reject it")

    return written, warnings
