"""Rubric parsing (design doc section 3.4).

Rubric files are markdown in the ``Structure / Style / Substance + Negative``
format. This module is the ONLY rubric reader — no second format is allowed.

Format (permissive about numbering, strict about structure):

    # <item-id> rubric — <title>

    ## Affirmative Points

    ### 1. Structure (格式与结构)
    - 1 pt  <question>
    - 1 pt  <question>

    ### 2. Style (风格)
    - N/A                    # this section contributes 0 points

    ### 3. Substance (实质)
    #### 3a. 价款与支付
    - 2 pts <question> 【对照 协议第3条】

    ## Negative Points
    - -1 pt  [HALLUC_FACT]  每处事实性错误...
    - -0.5 pt [EXTRATEXT]   每处冗余表述...

Affirmative lines: ``<points> pt(s) <text>`` and the points are *added*.
Negative lines: must carry a ``[CODE]`` drawn from the closed taxonomy
(negatives.py) and the points are *subtracted*.
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from pathlib import Path

from . import negatives

_HEADER_ID = re.compile(r"^#\s+(\S+)\s+rubric", re.MULTILINE)
_SECTION = re.compile(r"^##\s+(.+?)\s*$", re.MULTILINE)
_SUBSECTION = re.compile(r"^###+\s+(.+?)\s*$", re.MULTILINE)

# Leading bullet/serial, then points, then trailing text. "1 pt" / "1.5 pts" / "+2 pts".
_AFFIRM = re.compile(
    r"^[-*]?\s*\+?(\d+(?:\.\d+)?)\s*(?:pt|pts|point|points)\b\s*(.*)$",
    re.IGNORECASE,
)
_NEG = re.compile(
    r"^[-*]?\s*-(\d+(?:\.\d+)?)\s*(?:pt|pts|point|points)\b\s*(.*)$",
    re.IGNORECASE,
)
_CODE = re.compile(r"\[([A-Z_]+)\]")
_NA = re.compile(r"^\s*[-*]?\s*(?:N/?A|n/a|无|—|-)\s*$", re.IGNORECASE)


@dataclass
class AffirmativePoint:
    section: str          # "Structure" / "Style" / "Substance"
    subsection: str       # "3a. 价款与支付" or ""
    points: float
    text: str             # the gradeable proposition

    @property
    def key(self) -> str:
        return f"aff:{self.subsection or self.section}:{self.text}"


@dataclass
class NegativePoint:
    code: str             # from the closed taxonomy
    points: float         # positive magnitude; subtracted at scoring time
    text: str

    @property
    def key(self) -> str:
        return f"neg:{self.code}:{self.text}"


@dataclass
class Rubric:
    item_id: str
    title: str
    affirmative: list[AffirmativePoint] = field(default_factory=list)
    negative: list[NegativePoint] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    @property
    def max_positive_points(self) -> float:
        return round(sum(p.points for p in self.affirmative), 6)

    def rubric_hash(self) -> str:
        payload = "\n".join(
            [f"A|{p.section}|{p.subsection}|{p.points:g}|{p.text}" for p in self.affirmative]
            + [f"N|{n.code}|{n.points:g}|{n.text}" for n in self.negative]
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _section_kind(name: str) -> str | None:
    """Classify a section header into structure/style/substance/negative."""
    low = name.lower()
    if "negative" in low or "扣分" in name or "负面" in name:
        return "negative"
    if "structure" in low or "结构" in name or "格式" in name:
        return "structure"
    if "style" in low or "风格" in name or "语体" in name:
        return "style"
    if "substance" in low or "实质" in name:
        return "substance"
    if "affirmative" in low or "得分" in name or "正面" in name:
        return "affirmative"  # bare grouping header; classify children by position
    return None


def parse_rubric_text(text: str, *, source: str = "<string>") -> Rubric:
    lines = text.splitlines()

    m = _HEADER_ID.search(text)
    item_id = m.group(1) if m else ""
    title = ""
    if lines and lines[0].startswith("# "):
        title = lines[0][2:].strip()

    rubric = Rubric(item_id=item_id, title=title)

    section: str | None = None      # current ## category
    subsection: str | None = None   # current ###+ label
    sub_kind: str | None = None     # structure/style/substance for ### headers

    def cur_section_name() -> str:
        return (sub_kind or section or "substance").capitalize()

    for raw in lines:
        line = raw.rstrip()
        if not line.strip():
            continue

        sec = _SECTION.match(line)
        if sec:
            section = _section_kind(sec.group(1))
            subsection = None
            sub_kind = None
            continue

        sub = _SUBSECTION.match(line)
        if sub:
            label = sub.group(1)
            kind = _section_kind(label)
            if kind in {"structure", "style", "substance"}:
                sub_kind = kind
                subsection = None
            else:
                # a real sub-label like "3a. 价款与支付" under Substance
                subsection = label
            continue

        if section == "negative":
            neg = _parse_negative(line)
            if neg is not None:
                rubric.negative.append(neg)
            elif not _NA.match(line):
                rubric.warnings.append(f"unparsed negative line: {line.strip()!r}")
            continue

        if section in {"affirmative", "structure", "style", "substance", None}:
            aff = _parse_affirmative(line, cur_section_name(), subsection or "")
            if aff is not None:
                rubric.affirmative.append(aff)
            elif not _NA.match(line) and not line.lstrip().startswith("#"):
                rubric.warnings.append(f"unparsed affirmative line: {line.strip()!r}")

    return rubric


def _parse_affirmative(line: str, section: str, subsection: str) -> AffirmativePoint | None:
    m = _AFFIRM.match(line.strip())
    if not m:
        return None
    return AffirmativePoint(
        section=section,
        subsection=subsection,
        points=float(m.group(1)),
        text=m.group(2).strip(),
    )


def _parse_negative(line: str) -> NegativePoint | None:
    m = _NEG.match(line.strip())
    if not m:
        return None
    points = float(m.group(1))
    rest = m.group(2).strip()
    cm = _CODE.search(rest)
    if cm:
        code = cm.group(1)
        text = _CODE.sub("", rest).strip()
    else:
        # No explicit code: fall back to the generic fabrication category but
        # leave a marker so `validate` can flag the rubric.
        code = "HALLUC_FACT"
        text = "【缺少负分代码】" + rest
    return NegativePoint(code=code, points=points, text=text)


def parse_rubric_file(path: str | Path) -> Rubric:
    p = Path(path)
    return parse_rubric_text(p.read_text(encoding="utf-8"), source=str(p))


def validate_rubric(rubric: Rubric, expected_id: str | None = None) -> list[str]:
    """Structural checks on a parsed rubric. Empty list = valid."""
    problems: list[str] = []
    if not rubric.affirmative:
        problems.append("rubric has no affirmative points")
    if expected_id and rubric.item_id and rubric.item_id != expected_id:
        problems.append(
            f"rubric id {rubric.item_id!r} != expected {expected_id!r}"
        )
    for n in rubric.negative:
        if n.code not in negatives.CODES:
            problems.append(
                f"unknown negative code {n.code!r}; allowed: {sorted(negatives.CODES)}"
            )
        if not n.text or n.text.startswith("【缺少负分代码】"):
            problems.append(f"negative line missing [CODE]: {n.text!r}")
    return problems


def render_worksheet(item_id: str, rubric: Rubric, *, response_path: str = "") -> str:
    """Human grading worksheet (design doc section 3.6/3.7).

    Emitted by ``run --judge manual`` when no verdicts file is supplied. The
    reviewer marks each affirmative line yes/no and each negative category with
    a count; the result is a verdicts file that ``run --verdicts`` consumes.
    """
    out: list[str] = []
    out.append(f"# Grading worksheet — {item_id}")
    if response_path:
        out.append(f"\n_Response under review: `{response_path}`_\n")
    out.append("\n## Affirmative points  (mark  y / n )\n")
    section = None
    for p in rubric.affirmative:
        head = p.section if p.subsection == "" else f"{p.section} / {p.subsection}"
        if head != section:
            out.append(f"\n### {head}")
            section = head
        out.append(f"- [ ] ({p.points:g} pt) {p.text}")
    out.append("\n## Negative points  (enter a count per category)\n")
    for n in rubric.negative:
        out.append(f"- ({n.points:g} pt) [{n.code}] {n.text}  → count: ___")
    out.append("\n## Verdicts file format\n")
    out.append("```json")
    out.append('{')
    out.append(f'  "item_id": "{item_id}",')
    out.append('  "affirmative": {')
    out.extend(_json_entries([f'    "{_escape_key(p.key)}": true' for p in rubric.affirmative]))
    out.append('  },')
    out.append('  "negative": {')
    out.extend(_json_entries([f'    "{_escape_key(n.key)}": 0' for n in rubric.negative]))
    out.append('  }')
    out.append('}')
    out.append("```")
    return "\n".join(out)


def _json_entries(lines: list[str]) -> list[str]:
    """Comma between entries only — the block is meant to be pasted and parsed."""
    last = len(lines) - 1
    return [line + ("," if i != last else "") for i, line in enumerate(lines)]


def _escape_key(s: str) -> str:
    return s.replace("\\", "\\\\").replace('"', '\\"')
