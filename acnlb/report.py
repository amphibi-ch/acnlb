"""Report rendering (design doc section 3.8): per-item AND per-track, never only a mean."""

from __future__ import annotations

import json
from pathlib import Path

from .runner import bootstrap_ci


def load_results(path: str | Path) -> dict:
    return json.loads(Path(path).read_text(encoding="utf-8"))


def render_markdown(results: dict) -> str:
    run = results
    items = run.get("items", [])
    scored = [i for i in items if not i.get("error")]
    pcts = [i["pct"] for i in scored]
    lo, hi = bootstrap_ci(pcts)

    lines: list[str] = []
    lines.append(f"# acnlb run report — `{run.get('run_id','?')}`")
    lines.append("")
    lines.append(f"- Model: `{run.get('model','?')}`  @ `{run.get('base_url','?')}`")
    lines.append(f"- Judge: `{run.get('judge_mode','?')}`")
    lines.append(f"- Started: {run.get('started_at','?')}")
    v = run.get("versions", {})
    lines.append(
        f"- Versions: acnlb {v.get('acnlb','?')}, protocol {v.get('protocol','?')}, "
        f"schema {v.get('schema','?')}"
    )
    lines.append(f"- Items scored: **{len(scored)}/{len(items)}**")
    if scored:
        overall = 100.0 * sum(i["score"] for i in scored) / sum(i["max_positive_points"] for i in scored)
        lines.append(f"- Overall: **{overall:.1f}%** (95% CI {lo:.1f}–{hi:.1f})")
    lines.append("")

    if run.get("notes"):
        for n in run["notes"]:
            lines.append(f"> ⚠️ {n}")
        lines.append("")

    # per-track
    pt = run.get("per_track", {})
    if pt:
        lines.append("## Per-track")
        lines.append("")
        lines.append("| Track | Items | Score | % |")
        lines.append("|---|---:|---:|---:|")
        for track, t in sorted(pt.items()):
            lines.append(f"| {track} | {t['n']} | {t['earned']:g}/{t['max']:g} | {t['pct']:.1f}% |")
        lines.append("")

    # per-item
    lines.append("## Per-item")
    lines.append("")
    lines.append("| Item | Track | Task type | Ctx | Score | Max | % | Neg |")
    lines.append("|---|---|---|:-:|---:|---:|---:|---:|")
    for i in items:
        if i.get("error"):
            lines.append(
                f"| `{i['item_id']}` | {i['track']} | {i['task_type']} | "
                f"{'✓' if i['has_context'] else '—'} | **ERROR** | | | {i['error'][:60]} |"
            )
            continue
        lines.append(
            f"| `{i['item_id']}` | {i['track']} | {i['task_type']} | "
            f"{'✓' if i['has_context'] else '—'} | {i['score']:g} | "
            f"{i['max_positive_points']:g} | {i['pct']:.1f}% | {i['negative_total']:g} |"
        )
    lines.append("")
    lines.append("_Scoring: Σ(affirmative points hit) − Σ(negative points), floored at 0. "
                 "One number is never the whole story — read the track breakdown._")
    return "\n".join(lines)


def write_report(results: dict, out_path: str | Path) -> Path:
    out = Path(out_path)
    out.write_text(render_markdown(results), encoding="utf-8")
    return out
