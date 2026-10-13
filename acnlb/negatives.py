"""The closed CN negative-point taxonomy (design doc section 3.5).

This is the single source of truth for negative-point codes. Every rubric that
carries a negative point must name one of these codes; ``validate`` rejects any
other. Keeping the vocabulary closed is what makes scores comparable across
tasks, reviewers, and time.

Points shown here are the defaults. A rubric may override the default on an
individual line (e.g. FORMAT_BREACH is task-specific), but the *code* is fixed.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class NegativeCategory:
    code: str
    points: float
    label_zh: str
    label_en: str
    description: str


# Ordered as in the design doc table so the worksheet reads the same way.
TAXONOMY: tuple[NegativeCategory, ...] = (
    NegativeCategory(
        "HALLUC_FACT", -1.0, "编造事实", "Fabricated fact",
        "编造合同/文件里不存在的事实、条款、数字",
    ),
    NegativeCategory(
        "HALLUC_CITE", -1.0, "编造引用", "Fabricated citation",
        "编造不存在的法条、案号、司法解释",
    ),
    NegativeCategory(
        "REPEALED_LAW", -1.0, "引用已废止法律", "Repealed law cited",
        "引用已废止法律（如《合同法》《担保法》）或旧版本条文",
    ),
    NegativeCategory(
        "WRONG_HIERARCHY", -1.0, "效力位阶错误", "Authority-hierarchy error",
        "把非约束性来源当约束性（参考性案例当指导性案例、地方性文件当司法解释）",
    ),
    NegativeCategory(
        "EXTRATEXT", -0.5, "冗余/错误引申", "Extraneous or misconstrued",
        "准确但无关或错误引申的冗余表述",
    ),
    NegativeCategory(
        "FORMAT_BREACH", 0.0, "格式违规", "Format breach",
        "未满足明确格式要求（长度下限、必含小节）；分值由任务自定义",
    ),
)

BY_CODE: dict[str, NegativeCategory] = {c.code: c for c in TAXONOMY}

# The set of codes a rubric line is allowed to name.
CODES: frozenset[str] = frozenset(BY_CODE)

# Codes whose default score is task-defined; a rubric line must supply points.
TASK_DEFINED: frozenset[str] = frozenset(
    c.code for c in TAXONOMY if c.code == "FORMAT_BREACH"
)


def default_points(code: str) -> float:
    """Default negative points for ``code`` (negative number or 0)."""
    return BY_CODE[code].points


def describe(code: str) -> str:
    cat = BY_CODE[code]
    return f"{cat.code} ({cat.label_zh} / {cat.label_en}) pts={cat.points}: {cat.description}"


def as_table() -> str:
    """Render the taxonomy as a markdown table for the site/README."""
    rows = ["| Code | Error | Points |", "|---|---|---|"]
    for c in TAXONOMY:
        pts = "task-specific" if c.code in TASK_DEFINED else f"{c.points:g}"
        rows.append(f"| `{c.code}` | {c.label_zh} / {c.label_en} | {pts} |")
    return "\n".join(rows)
