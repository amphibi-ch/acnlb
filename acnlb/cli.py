"""CLI — the single source of truth. GitHub Actions shells out to exactly this.

    python -m acnlb run      --items items/sample --model models.example.yaml ...
    python -m acnlb score    --response <fixture> --rubric <fixture>
    python -m acnlb report   --run runs/<id> [--markdown]
    python -m acnlb validate --items items/sample
    python -m acnlb judge-validate --labels <path> [--min-kappa 0.6]
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .judge import validate_judge
from .model import ModelClient, ModelConfig
from .report import render_markdown, write_report
from .rubric import parse_rubric_file, render_worksheet, validate_rubric
from .runner import run as run_eval
from .runner import write_run
from .scaffold import scaffold
from .schema import load_items, validate_item
from .scorer import canonical_json, score


def _default_root() -> Path:
    """Repo root = the directory containing the ``acnlb`` package."""
    return Path(__file__).resolve().parent.parent


def cmd_run(args: argparse.Namespace) -> int:
    root = _default_root()
    items_root = Path(args.items).resolve()
    items = load_items(items_root)
    if args.limit:
        items = items[: args.limit]
    if not items:
        print("error: no items found", file=sys.stderr)
        return 2

    model_config = ModelConfig.from_yaml(args.model, name=args.model_name)
    out_dir = Path(args.out) if args.out else Path("runs") / "latest"

    verdicts_dir = Path(args.verdicts).resolve() if args.verdicts else None

    # manual mode with no verdicts → export worksheets and stop (design doc section 3.6)
    if args.judge == "manual" and verdicts_dir is None:
        ws_dir = Path(args.worksheet) if args.worksheet else out_dir / "worksheets"
        ws_dir.mkdir(parents=True, exist_ok=True)
        for item in items:
            rubric = parse_rubric_file(items_root / item.rubric)
            ws = render_worksheet(item.id, rubric)
            (ws_dir / f"{item.id}.worksheet.md").write_text(ws, encoding="utf-8")
        print(f"Exported {len(items)} grading worksheet(s) to {ws_dir}")
        print("Grade them, then re-run with --verdicts <dir>/ containing <id>.verdicts.json")
        return 0

    judge_client = None
    if args.judge == "llm":
        judge_cfg = ModelConfig.from_yaml(args.judge_model or args.model, name=args.model_name)
        judge_client = ModelClient(judge_cfg)

    result = run_eval(
        items,
        items_root,
        model_config=model_config,
        judge_mode=args.judge,
        verdicts_dir=verdicts_dir,
        responses_dir=Path(args.responses).resolve() if args.responses else None,
        judge_client=judge_client,
        run_id=args.run_id,
        limit=None,
    )
    results_path = write_run(result, out_dir)
    report_path = write_report(json.loads(results_path.read_text("utf-8")), out_dir / "report.md")

    scored = result.scored_count
    print(f"Scored {scored}/{len(result.items)} items → {results_path}")
    print(f"Report → {report_path}")
    if result.notes:
        for n in result.notes:
            print(f"WARNING: {n}", file=sys.stderr)
    if scored == 0:
        print("error: zero items scored", file=sys.stderr)
        return 3
    if scored < len(result.items):
        print(f"error: {len(result.items) - scored} item(s) errored", file=sys.stderr)
        return 4
    return 0


def cmd_score(args: argparse.Namespace) -> int:
    rubric = parse_rubric_file(args.rubric)
    verdicts: dict = {}
    if args.verdicts:
        verdicts = json.loads(Path(args.verdicts).read_text(encoding="utf-8"))
    elif args.response:
        # If a sidecar verdicts file exists next to the response, use it; scoring
        # a raw response with no verdicts means "nothing hit" and is still valid.
        side = Path(args.response).with_suffix(".verdicts.json")
        if side.exists():
            verdicts = json.loads(side.read_text(encoding="utf-8"))

    iscore = score(
        rubric,
        affirmative=verdicts.get("affirmative", {}),
        negative=verdicts.get("negative", {}),
    )
    if args.json:
        print(canonical_json(iscore))
    else:
        print(f"{iscore.item_id}: {iscore.score:g}/{iscore.affirmative_max:g} "
              f"(earned {iscore.affirmative_earned:g}, neg −{iscore.negative_total:g})")
    return 0


def cmd_report(args: argparse.Namespace) -> int:
    run_dir = Path(args.run)
    results_path = run_dir / "results.json" if run_dir.is_dir() else run_dir
    results = json.loads(results_path.read_text(encoding="utf-8"))
    if args.markdown:
        md_path = results_path.parent / "report.md"
        write_report(results, md_path)
        print(f"Wrote {md_path}")
    else:
        print(render_markdown(results))
    return 0


def cmd_new(args: argparse.Namespace) -> int:
    """Scaffold an item directory from a plain-text intake form."""
    try:
        written, warnings = scaffold(
            args.intake, args.out, item_id=args.id, force=args.force
        )
    except (ValueError, FileExistsError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1
    for p in written:
        print(f"wrote {p}")
    for w in warnings:
        print(f"WARNING: {w}", file=sys.stderr)
    print(
        "\nNext: fill the gold answer first, then the rubric (design doc §3.6), "
        f"then run:  python -m acnlb validate --items {args.out}"
    )
    return 0


def cmd_validate(args: argparse.Namespace) -> int:
    items_root = Path(args.items).resolve()
    items = load_items(items_root)
    problems: list[str] = []
    for item in items:
        for p in validate_item(item, items_root):
            problems.append(f"{item.id}: {p}")
        rubric = parse_rubric_file(items_root / item.rubric)
        for p in validate_rubric(rubric, expected_id=item.id):
            problems.append(f"{item.id}: {p}")
        for a in rubric.affirmative:
            if "TODO" in a.text:
                problems.append(f"{item.id}: affirmative point still a TODO placeholder: {a.text[:40]}")
        gold_path = items_root / item.gold_answer if item.gold_answer else None
        if gold_path and gold_path.exists() and "TODO" in gold_path.read_text(encoding="utf-8"):
            problems.append(f"{item.id}: gold answer still contains TODOs")
        if not item.is_synthetic and "sample" in str(items_root):
            problems.append(f"{item.id}: item under items/sample must be marked SYNTHETIC")
    if problems:
        for p in problems:
            print(f"FAIL {p}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s) across {len(items)} item(s)", file=sys.stderr)
        return 1
    print(f"OK — {len(items)} item(s) valid")
    return 0


def cmd_judge_validate(args: argparse.Namespace) -> int:
    report = validate_judge(args.labels, min_kappa=args.min_kappa)
    print(json.dumps(report.as_dict(), ensure_ascii=False, indent=2))
    if not report.validated:
        print(
            f"\nNOT VALIDATED: kappa {report.kappa:.3f} < {args.min_kappa}. "
            "Keep these items in the human-graded bucket.",
            file=sys.stderr,
        )
        return 1
    print(f"\nVALIDATED: kappa {report.kappa:.3f} >= {args.min_kappa}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="acnlb", description="alpha CN legal benchmark harness")
    p.add_argument("--version", action="version", version=f"acnlb {__version__}")
    sub = p.add_subparsers(dest="command", required=True)

    r = sub.add_parser("run", help="run the eval over an items directory")
    r.add_argument("--items", required=True, help="items dir or single item .json")
    r.add_argument("--model", required=True, help="model config YAML")
    r.add_argument("--model-name", default=None, help="named model entry in the config")
    r.add_argument("--judge", choices=["manual", "llm"], default="manual")
    r.add_argument("--judge-model", default=None, help="model config for the LLM judge")
    r.add_argument("--verdicts", default=None, help="dir of <id>.verdicts.json files")
    r.add_argument("--responses", default=None,
                   help="dir of frozen responses (<id>.txt / <id>.good.txt); skips the model call")
    r.add_argument("--worksheet", default=None, help="dir to write manual worksheets")
    r.add_argument("--out", default=None, help="output dir (default runs/latest)")
    r.add_argument("--run-id", default=None)
    r.add_argument("--limit", type=int, default=None)
    r.set_defaults(func=cmd_run)

    s = sub.add_parser("score", help="score one response against one rubric (pure)")
    s.add_argument("--response", default=None, help="response fixture path")
    s.add_argument("--rubric", required=True, help="rubric markdown path")
    s.add_argument("--verdicts", default=None, help="verdicts JSON path")
    s.add_argument("--json", action="store_true")
    s.set_defaults(func=cmd_score)

    rep = sub.add_parser("report", help="render a run's report")
    rep.add_argument("--run", required=True, help="run dir or results.json")
    rep.add_argument("--markdown", action="store_true", help="write report.md next to results")
    rep.set_defaults(func=cmd_report)

    v = sub.add_parser("validate", help="validate items + rubrics")
    v.add_argument("--items", required=True)
    v.set_defaults(func=cmd_validate)

    n = sub.add_parser("new", help="scaffold an item from a plain-text intake form")
    n.add_argument("--intake", required=True, help="intake markdown (see items/INTAKE.template.md)")
    n.add_argument("--out", required=True, help="items dir to write into")
    n.add_argument("--id", default=None, help="override the id from the form")
    n.add_argument("--force", action="store_true", help="overwrite existing files")
    n.set_defaults(func=cmd_new)

    jv = sub.add_parser("judge-validate", help="compute Cohen's kappa for the LLM judge")
    jv.add_argument("--labels", required=True)
    jv.add_argument("--min-kappa", type=float, default=0.6)
    jv.set_defaults(func=cmd_judge_validate)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return args.func(args)


if __name__ == "__main__":
    raise SystemExit(main())
