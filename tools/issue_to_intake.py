#!/usr/bin/env python3
"""Turn a filled-in issue form into item files — the same ones `acnlb new` writes.

The form is `.github/ISSUE_TEMPLATE/new-item.yml`; GitHub renders it into the
issue body as `### <label>` followed by what was typed, with `_No response_` for
what was left blank. This reads that back and hands the result to
`acnlb.scaffold`, so the files are byte-identical to the CLI's output rather than
a third implementation of the same shape.

Two things make that safe to run on text a stranger typed:

* the **id becomes a file name**, so it is checked against `acnlb.schema`
  before anything is written, and a blank one is filled from the item set's own
  numbering (`acnlb.vocab.next_id`) instead of being invented;
* **attachment paths must stay inside the items directory** (`scaffold` refuses
  the rest), because `validate` resolves them against it.

Parameters are all overridable, because this is also the local debugging path —
`--body` a saved issue body, `--out` anywhere, `--reference` to number after a
different set. The output directory is written with `force`: the Action rebuilds
the branch from the issue on every edit, so re-running over the same id is the
intended path, not an accident.

Run:  python tools/issue_to_intake.py --body issue.md --out items/incoming
      python tools/issue_to_intake.py --body issue.md --out /tmp/x --intake-out /tmp/x.intake.md
"""
from __future__ import annotations

import argparse
import json
import sys
import tempfile
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:  # tools/ is not a package; run as a script
    sys.path.insert(0, str(ROOT))

from acnlb.schema import id_problem  # noqa: E402
from acnlb.scaffold import scaffold  # noqa: E402
from acnlb.vocab import build_vocab, next_id  # noqa: E402

DEFAULT_TEMPLATE = ".github/ISSUE_TEMPLATE/new-item.yml"
DEFAULT_OUT = "items/incoming"
# Where the numbering convention is read from when the target set is empty: the
# first item of a new set should still be numbered like the published ones.
REFERENCE_SET = "items/bench10"

# Fields that become intake header lines, in the intake template's order. The
# rest of the form goes into a `## Section` — see SECTION_FIELDS. Every field id
# in the issue form has to be in one of the two: a test reads the form and fails
# on an id this file does not know, which is what caught `item_id` being written
# while the intake key was `id` (the contributor's id was silently replaced by a
# generated one).
HEADER_FIELDS = ("id", "track", "category", "task_type", "task", "jurisdiction", "authority_basis")

# Field id → the heading `parse_intake` expects. A test asserts every one of these
# headings is in the parser's own vocabulary, and that no template field is
# unaccounted for, so adding a field to the form forces a decision here.
SECTION_FIELDS = {
    "prompt": "## Prompt",
    "documents": "## Documents",
    "gold": "## Gold answer",
    "rubric": "## Rubric",
    "retrieval_gold": "## Retrieval gold",
    "notes": "## Notes",
}

NO_RESPONSE = "_No response_"

# A rubric plus three documents is a few kilobytes; anything at this size is not a
# form submission, and it would be copied into a commit.
MAX_BODY = 200_000


class ToolError(Exception):
    """Something the contributor can fix — reported as-is, never as a stack trace."""


def rel(path: Path) -> str:
    try:
        return path.relative_to(ROOT).as_posix()
    except ValueError:
        return str(path)


def load_template(path: Path) -> dict[str, Any]:
    try:
        import yaml
    except ImportError as exc:  # pragma: no cover - CI installs it
        raise ToolError(f"PyYAML is required to read the issue template: {exc}") from exc

    if not path.is_file():
        raise ToolError(f"issue template not found: {rel(path)}")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict) or not isinstance(data.get("body"), list):
        raise ToolError(f"{rel(path)} is not an issue form (no `body:` list)")
    return data


def field_labels(template: dict[str, Any]) -> dict[str, str]:
    """`{label text: field id}` — the form's own mapping, not a second copy.

    The issue body carries labels, not ids, so this is the only place the two can
    be related without writing the labels down twice.
    """
    out: dict[str, str] = {}
    for item in template.get("body") or []:
        if not isinstance(item, dict) or item.get("type") == "markdown":
            continue
        attrs = item.get("attributes") or {}
        label, fid = attrs.get("label"), item.get("id")
        if label and fid:
            out[str(label).strip()] = str(fid)
    return out


def parse_issue(body: str, labels: dict[str, str]) -> dict[str, str]:
    """Issue body → `{field id: text}`.

    A `### ` line starts a field only when it matches a label in the form, so a
    rubric section heading inside a textarea stays part of that textarea.
    """
    values: dict[str, str] = {}
    current: str | None = None
    buf: list[str] = []

    def flush() -> None:
        if current is None:
            return
        text = "\n".join(buf).strip()
        values[current] = "" if text == NO_RESPONSE else text

    for raw in body.splitlines():
        line = raw.rstrip()
        if line.startswith("### ") and line[4:].strip() in labels:
            flush()
            current = labels[line[4:].strip()]
            buf = []
            continue
        if current is not None:
            buf.append(line)
    flush()
    return values


def one_line(text: str) -> str:
    """Header lines are single lines: collapse anything pasted with newlines."""
    return " ".join((text or "").split())


def to_intake(values: dict[str, str], item_id: str) -> str:
    """The intake form `acnlb new --intake` consumes."""
    out: list[str] = []
    for key in HEADER_FIELDS:
        # `id` is written from the resolved value: the form may have left it blank
        # and had one assigned, and writing the raw field back would undo that.
        out.append(f"id: {item_id}" if key == "id" else f"{key}: {one_line(values.get(key, ''))}")

    for key, heading in SECTION_FIELDS.items():
        text = (values.get(key) or "").strip()
        # An empty `## Retrieval gold` is not an absent section: the parser reads
        # it and rejects it for having no `class:`. Omit it instead, so a
        # non-retrieval item simply does not carry one and a retrieval item gets
        # scaffold's own "needs a Retrieval gold section" message.
        if not text and key == "retrieval_gold":
            continue
        out += ["", heading, ""]
        if not text:
            continue
        if key == "documents":
            for raw in text.splitlines():
                entry = raw.strip().lstrip("-*").strip()
                if entry:
                    out.append(f"- {entry}")
        else:
            out += text.splitlines()
    return "\n".join(out) + "\n"


def set_vocab(reference: Path, out_dir: Path) -> dict[str, Any]:
    """The vocabulary to suggest from, and the numbers to continue.

    The **reference set comes first, and that order is the point.** Reading the
    target directory first looks harmless and is not: `items/incoming/` is a
    scratch area a run has just written to, so the second run over the same issue
    would find the first run's file, call `core-tx-0003` taken and propose
    `core-tx-0004`. A different id on every edit means a different branch and a
    second pull request out of the same issue — so the id has to be a function of
    the submission, not of how many times the tool has been run.

    The target directory is still consulted, but only when the reference set has
    nothing to say: a brand-new benchmark still needs *some* convention, and
    `DEFAULT_WIDTH` is a worse answer than "whatever is already there".
    """
    for directory in (reference, out_dir):
        raws: list[dict[str, Any]] = []
        if directory.is_dir():
            for path in sorted(directory.glob("*.json")):
                if path.name.startswith("_"):
                    continue
                try:
                    raws.append(json.loads(path.read_text(encoding="utf-8")))
                except (OSError, json.JSONDecodeError):
                    continue
        if raws:
            return build_vocab(raws)
    return build_vocab([])


def build(
    body: str,
    out_dir: Path,
    template_path: Path,
    *,
    intake_out: Path | None,
    reference: Path | None = None,
) -> dict[str, Any]:
    if len(body) > MAX_BODY:
        raise ToolError(f"issue body is {len(body)} bytes; the limit is {MAX_BODY}")

    values = parse_issue(body, field_labels(load_template(template_path)))
    if not values:
        raise ToolError(
            "no form field matched this issue body — was the issue opened from the "
            "「投稿一道题集」 form?"
        )

    item_id = one_line(values.get("id", ""))
    if item_id:
        problem = id_problem(item_id)
        if problem:
            raise ToolError(problem)
    else:
        item_id = next_id(
            set_vocab(reference or (ROOT / REFERENCE_SET), out_dir),
            track=one_line(values.get("track", "")),
            category=one_line(values.get("category", "")),
        )
        if not item_id:
            raise ToolError("no id in the form and none could be suggested; fill in 「编号 id」")

    intake_text = to_intake(values, item_id)
    if intake_out:
        intake_out.parent.mkdir(parents=True, exist_ok=True)
        intake_out.write_text(intake_text, encoding="utf-8")

    with tempfile.TemporaryDirectory(prefix="acnlb-intake-") as tmp:
        form = Path(tmp) / f"{item_id}.intake.md"
        form.write_text(intake_text, encoding="utf-8")
        # force: the branch is rebuilt from the issue on every edit, so the second
        # run over the same id is the intended path, not an accident.
        written, warnings = scaffold(form, out_dir, item_id=item_id, force=True)

    return {
        "ok": True,
        "id": item_id,
        "items_dir": rel(out_dir),
        "intake": rel(intake_out) if intake_out else "",
        "written": [rel(p) for p in written],
        "warnings": warnings,
        "errors": [],
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--body", required=True,
                    help="file holding the issue body (the workflow writes it from the event)")
    ap.add_argument("--out", default=DEFAULT_OUT, help="item set to write into")
    ap.add_argument("--template", default=DEFAULT_TEMPLATE, help="issue form defining the field labels")
    ap.add_argument("--reference", default=REFERENCE_SET,
                    help="set whose numbering and vocabulary to follow (default: the published set)")
    ap.add_argument("--intake-out", default=None, help="also keep the generated intake form here")
    ap.add_argument("--report", default=None, help="write a JSON report here (ok/id/written/errors)")
    args = ap.parse_args()

    out_dir = (ROOT / args.out).resolve()
    template_path = Path(args.template)
    if not template_path.is_absolute():
        template_path = ROOT / template_path
    reference = Path(args.reference)
    if not reference.is_absolute():
        reference = ROOT / reference
    intake_out = Path(args.intake_out).resolve() if args.intake_out else None

    report: dict[str, Any]
    try:
        body = Path(args.body).read_text(encoding="utf-8")
        report = build(body, out_dir, template_path, intake_out=intake_out, reference=reference)
    except ToolError as exc:
        report = {"ok": False, "id": "", "errors": [str(exc)], "written": [], "warnings": []}
    except (ValueError, FileExistsError) as exc:
        report = {"ok": False, "id": "", "errors": [str(exc)], "written": [], "warnings": []}

    if args.report:
        path = Path(args.report).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")

    if not report["ok"]:
        for err in report["errors"]:
            print(f"error: {err}", file=sys.stderr)
        print("\n修正 issue 表单后编辑该 issue，Action 会重新生成。", file=sys.stderr)
        return 1

    for path in report["written"]:
        print(f"wrote {path}")
    for warning in report["warnings"]:
        print(f"WARNING: {warning}", file=sys.stderr)
    print(f"\n{report['items_dir']} ← issue 表单（id={report['id']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
