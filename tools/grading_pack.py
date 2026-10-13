"""Merge one grading pack: each item's checklist next to the model's answer.

Grading is the one step the harness cannot do for you, and doing it needs three
things at once — what was asked, what came back, and the exact point-by-point
checklist. Those live in the items dir, the responses dir, and a worksheet, so
ten items means twenty files open at once. This joins them into one read-only
document.

It scores nothing and writes no verdicts: a pack is a reading surface.

Run:
    python tools/grading_pack.py --items items/bench10 \
        --responses <answers-dir> \
        --verdicts <verdicts-dir> \
        --out <answers-dir>/GRADING.md
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb.rubric import parse_rubric_file, render_worksheet  # noqa: E402
from acnlb.runner import find_response  # noqa: E402
from acnlb.schema import load_items  # noqa: E402

TRACK_LABELS = {"core": "核心", "workflows": "工作流", "retrieval": "检索"}


def _clip(worksheet: str) -> str:
    """The checklist half of a worksheet, demoted one heading level.

    Everything from ``## Verdicts file format`` on is dropped: the reviewer
    edits the verdicts file on disk, and ten copies of a 15-key JSON block
    would triple the length of the pack for no reading value.
    """
    head, _, body = worksheet.partition("\n")
    body = body.split("\n## Verdicts file format", 1)[0].rstrip()
    lines = [("#" + ln) if ln.startswith("#") else ln for ln in body.split("\n")]
    return "\n".join(lines)


def _shown(path: Path) -> str:
    """Repo-relative when possible, absolute otherwise — for embedding in docs."""
    try:
        return str(path.relative_to(ROOT))
    except ValueError:
        return str(path)


def build(items_root: Path, responses_dir: Path, verdicts_dir: Path) -> str:
    items = load_items(items_root)
    out: list[str] = []

    rows: list[str] = []
    bodies: list[str] = []
    for item in items:
        rubric = parse_rubric_file(items_root / item.rubric)
        rpath = find_response(responses_dir, item.id)
        answer = rpath.read_text(encoding="utf-8") if rpath else ""
        flag = "" if rpath else "  ← 找不到作答文件"
        rows.append(
            f"| `{item.id}` | {TRACK_LABELS.get(item.track, item.track)} | {item.task_type} "
            f"| {rubric.max_positive_points:g} | {len(answer)} |"
        )
        bodies.append(
            "\n".join(
                [
                    f"\n---\n\n## `{item.id}` — {item.task_type}（{rubric.max_positive_points:g} 分）{flag}",
                    f"\n**题目**：{item.task}\n",
                    f"\n### 模型作答（`{rpath.relative_to(ROOT) if rpath else '—'}`，"
                    f"{len(answer)} 字符）\n",
                    "```text",
                    answer.rstrip("\n"),
                    "```\n",
                    f"\n### 判分清单  → 改 `{(verdicts_dir / f'{item.id}.verdicts.json').relative_to(ROOT)}`\n",
                    _clip(render_worksheet(item.id, rubric)),
                ]
            )
        )

    out.append(f"# {items_root.name} 判分包\n")
    out.append(
        "每道题一节：**题目 → 模型作答 → 判分清单**。判分是把清单里的成立项 `[ ]` 改成 "
        "`[x]`、负分项填 count，然后写回对应 verdicts JSON（key 已预填，只改 true/false 和数字）。\n"
    )
    out.append("\n## 总览\n")
    out.append("| 题号 | 轨道 | 任务 | 判分点 | 作答字符数 |")
    out.append("|---|---|---|---:|---:|")
    out.extend(rows)
    out.append(
        f"\n合计 {sum(parse_rubric_file(items_root / i.rubric).max_positive_points for i in items):g} 个判分点。"
        "注意 retrieval 轨还有一栏**自动**引证匹配分（高 2 / 中 1 / 低 0.5），"
        "不计入上表，判分时别与手工分混在一起。\n"
    )
    out.append(
        "\n填完 verdicts 后跑：\n\n```bash\n"
        f"./.venv/bin/python -m acnlb run --items {items_root.name} \\\n"
        "  --model models.example.yaml --judge manual \\\n"
        f"  --responses {_shown(responses_dir)} \\\n"
        f"  --verdicts {_shown(verdicts_dir)} --out runs/latest\n```\n"
    )
    out.extend(bodies)
    return "\n".join(out) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--items", default="items/bench10")
    ap.add_argument("--responses", required=True, help="dir of <id>.txt answers")
    ap.add_argument("--verdicts", default=None, help="dir the reviewer will fill")
    ap.add_argument("--out", required=True, help="markdown file to write")
    args = ap.parse_args()

    out_path = (ROOT / args.out).resolve()
    verdicts_dir = (ROOT / args.verdicts).resolve() if args.verdicts else out_path.parent / "verdicts"
    text = build((ROOT / args.items).resolve(),
                 (ROOT / args.responses).resolve(),
                 verdicts_dir)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(text, encoding="utf-8")
    print(f"wrote {out_path.relative_to(ROOT)} ({len(text)} chars)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
