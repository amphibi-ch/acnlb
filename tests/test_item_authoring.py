"""Authoring surfaces: the rubric templates, the layout that describes them, and
the vocabulary derived from the item set.

Three things are being defended here, and they are all the same thing: a value
that exists in one place and is re-typed in another will drift, and the drift is
silent in the direction that matters — the tool keeps working, it just stops
agreeing with the file it is supposed to be describing.

* `RUBRIC_TEMPLATES` are offered to a drafter as a starting point, so each one has
  to parse, has to be rejected by `validate` until it is filled in (otherwise a
  template ships as a finished rubric), and has to use the same headings
  `RUBRIC_LAYOUT` tells the row editor to write.
* `RUBRIC_LAYOUT` is the *only* place the format's headings live. The web form
  emits markdown from it; if it stops matching the parser, the form writes a
  format the CLI cannot read.
* `build_vocab` answers "what do the items that already exist put in this field",
  and it is what both the browser and the issue-to-PR tool read. The set is the
  single source, so `site/items.json` may not carry a second, staler derivation.
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from acnlb import negatives  # noqa: E402
from acnlb.rubric import parse_rubric_text  # noqa: E402
from acnlb.scaffold import (  # noqa: E402
    DEFAULT_RUBRIC,
    RUBRIC_LAYOUT,
    RUBRIC_TEMPLATES,
    rubric_template,
    scaffold,
)
from acnlb.schema import VALID_TRACKS  # noqa: E402
from acnlb.vocab import DEFAULT_WIDTH, build_vocab, next_id  # noqa: E402

BENCH = ROOT / "items" / "bench10"
ITEMS_JSON = ROOT / "site" / "items.json"


def bench_raws() -> list[dict]:
    return [
        json.loads(p.read_text(encoding="utf-8"))
        for p in sorted(BENCH.glob("*.json"))
    ]


def rendered(template: str) -> str:
    return template.replace("{item_id}", "core-tx-9001").replace("{task}", "审查一份借款合同")


# ---------- templates ----------

def test_every_track_has_a_template() -> None:
    assert set(RUBRIC_TEMPLATES) == set(VALID_TRACKS)


@pytest.mark.parametrize("track", sorted(RUBRIC_TEMPLATES))
def test_a_template_is_a_draft_and_says_so(track: str) -> None:
    """`validate` refuses a TODO placeholder; a template is nothing but placeholders.

    So this asserts the template is *accepted by the parser* and *rejected by
    validate*, which are different questions and the second one is the one that
    keeps an unfilled template out of the item set.
    """
    text = rendered(RUBRIC_TEMPLATES[track])
    rubric = parse_rubric_text(text)

    assert rubric.affirmative, track
    assert rubric.warnings == [], (track, rubric.warnings)
    assert rubric.max_positive_points > 0, track
    assert "TODO" in text, track
    assert all("TODO" in a.text for a in rubric.affirmative), track

    # Every negative code is from the closed taxonomy, and a task-defined one
    # carries its own number rather than inheriting the taxonomy's 0.
    for n in rubric.negative:
        assert n.code in negatives.CODES, (track, n.code)
        assert n.text, (track, n.code)
        assert n.points > 0, (track, n.code)


def test_rubric_template_falls_back_to_the_generic_skeleton() -> None:
    assert rubric_template("nope") == DEFAULT_RUBRIC
    assert rubric_template("core") == RUBRIC_TEMPLATES["core"]


@pytest.mark.parametrize("track", sorted(RUBRIC_TEMPLATES))
def test_a_blank_rubric_gets_the_track_s_template(track: str, tmp_path: Path) -> None:
    """`acnlb new` and the web form must hand back the same draft.

    The page builds this string in JavaScript out of the exported templates; this
    is the Python half. If they drift, the same submission is a different rubric
    depending on which route made it — and nothing else would notice, because a
    skeleton is a skeleton until the TODO check runs.
    """
    from acnlb.scaffold import render_rubric_skeleton

    gold = "\n## Retrieval gold\n\nclass: statute\n\n- 高 | X | n\n" if track == "retrieval" else ""
    intake = tmp_path / "in.md"
    intake.write_text(
        f"id: {track}-9001\ntrack: {track}\ntask_type: 任务类型\ntask: 任务\n\n## Prompt\n\np\n{gold}",
        encoding="utf-8",
    )
    out = tmp_path / track
    written, warnings = scaffold(intake, out)

    text = (out / f"{track}-9001.rubric.md").read_text(encoding="utf-8")
    assert text == render_rubric_skeleton(track, f"{track}-9001", "任务")
    assert (out / f"{track}-9001.json").is_file()
    assert any("TODO" in w for w in warnings), warnings


# ---------- the layout ----------

def headings(text: str) -> set[str]:
    """Section and subsection headings, read with the layout's own markers."""
    found = set()
    for line in text.splitlines():
        if line.startswith(RUBRIC_LAYOUT["heading_level"] + " "):
            found.add(line)
        if line.startswith(RUBRIC_LAYOUT["subsection_level"] + " "):
            found.add(RUBRIC_LAYOUT["subsection_level"] + " <label>")
    return found


def test_the_layout_describes_every_writer() -> None:
    """The layout is what the row editor emits, so it has to match what exists.

    `DEFAULT_RUBRIC` and the three templates are the only skeletons in the repo;
    if the layout named different headings, the page would write a rubric whose
    sections the parser reclassifies — points landing under the wrong heading
    with nothing failing.
    """
    expected = headings(DEFAULT_RUBRIC)
    assert expected == {
        f"{RUBRIC_LAYOUT['heading_level']} {s['title']}" for s in RUBRIC_LAYOUT["sections"]
    }
    for track, tpl in RUBRIC_TEMPLATES.items():
        assert headings(tpl) - expected <= {RUBRIC_LAYOUT["subsection_level"] + " <label>"}, track

    # And the sections the layout names are the ones the parser derives from those
    # headings — that mapping is what lets a row be assigned back to its tab.
    parsed = parse_rubric_text(rendered(RUBRIC_TEMPLATES["core"]))
    named = {s["section"] for s in RUBRIC_LAYOUT["sections"]}
    assert {a.section for a in parsed.affirmative} <= named
    assert [s["key"] for s in RUBRIC_LAYOUT["sections"]] == ["structure", "style", "substance"]


def test_the_layout_round_trips_through_the_parser() -> None:
    """Writing the layout's own line shapes must produce a parseable rubric."""
    order = ["structure", "style", "substance"]
    lines = [
        RUBRIC_LAYOUT["title"].replace("{item_id}", "core-tx-9001").replace("{task}", "t"),
        "",
        RUBRIC_LAYOUT["affirmative_heading"],
        "",
    ]
    for key, sec in zip(order, RUBRIC_LAYOUT["sections"]):
        assert sec["key"] == key
        lines.append(f"{RUBRIC_LAYOUT['heading_level']} {sec['title']}")
        if key == "substance":
            lines.append(f"{RUBRIC_LAYOUT['subsection_level']} 3a. 小节")
            lines.append(RUBRIC_LAYOUT["affirmative_item"]
                         .replace("{points}", "2").replace("{unit}", "pts").replace("{text}", "一个命题"))
        else:
            lines.append(RUBRIC_LAYOUT["na"])
        lines.append("")
    lines.append(RUBRIC_LAYOUT["negative_heading"])
    lines.append(RUBRIC_LAYOUT["negative_item"]
                 .replace("{points}", "1").replace("{unit}", "pt")
                 .replace("{code}", "REPEALED_LAW").replace("{text}", "引用已废止法律"))
    lines.append("")

    rubric = parse_rubric_text("\n".join(lines))
    assert rubric.warnings == [], rubric.warnings
    assert rubric.item_id == "core-tx-9001"
    # Only the substance section carries a point here; the other two were written
    # as the layout's N/A, which means "no points", not "an unparsed line".
    assert [(a.section, a.subsection, a.points, a.text) for a in rubric.affirmative] == \
           [("Substance", "3a. 小节", 2.0, "一个命题")]
    assert rubric.max_positive_points == 2.0
    assert [n.code for n in rubric.negative] == ["REPEALED_LAW"]
    assert [n.points for n in rubric.negative] == [1.0]


# ---------- document paths ----------

@pytest.mark.parametrize("bad", ["../x", "docs/../x", "/etc/passwd", "\\a", "C:\\x", ".."])
def test_scaffold_refuses_a_document_path_that_escapes(bad: str, tmp_path: Path) -> None:
    """Checked before anything is written — a bad path must not reach a commit."""
    intake = tmp_path / "in.md"
    intake.write_text(
        "id: core-tx-9001\ntrack: core\ntask_type: 合同审查\ntask: t\n"
        f"\n## Prompt\n\np\n\n## Documents\n\n- {bad}\n",
        encoding="utf-8",
    )
    out = tmp_path / "items"
    with pytest.raises(ValueError, match="document path"):
        scaffold(intake, out)
    assert not out.exists() or not list(out.glob("*.json"))


def test_scaffold_accepts_a_relative_document_path(tmp_path: Path) -> None:
    intake = tmp_path / "in.md"
    intake.write_text(
        "id: core-tx-9001\ntrack: core\ntask_type: 合同审查\ntask: t\n"
        "\n## Prompt\n\np\n\n## Documents\n\n- docs/core-tx-9001-loan.md\n",
        encoding="utf-8",
    )
    written, warnings = scaffold(intake, tmp_path / "items")
    assert any(p.name == "core-tx-9001.json" for p in written)
    assert any("not found yet" in w for w in warnings), warnings


# ---------- vocabulary ----------

def test_vocab_lists_what_the_set_already_uses() -> None:
    vocab = build_vocab(bench_raws())
    assert vocab["jurisdictions"] == ["CN-mainland"]
    assert set(vocab["categories"]) == {"Litigation", "Transaction", "Workflow", "Retrieval"}
    assert vocab["task_types"], vocab
    assert vocab["authority_basis"], vocab
    assert all(d.startswith("docs/") for d in vocab["documents"]), vocab["documents"]

    # Every list is drawn from the set, so nothing can be suggested that no item
    # has ever used.
    assert set(vocab["categories"]) == {r["category"] for r in bench_raws() if r.get("category")}
    assert set(vocab["jurisdictions"]) == {r["jurisdiction"] for r in bench_raws() if r.get("jurisdiction")}
    assert set(vocab["task_types"]) == {r["task_type"] for r in bench_raws() if r.get("task_type")}


def test_vocab_examples_are_values_the_set_already_contains() -> None:
    """The form's grey hints come from here, and each one is a *value*, not a
    description: it is what gets typed if nobody overwrites it.

    A placeholder the set has never used is how the page starts teaching a
    shape no item has — the same failure as a hand-typed dropdown list, one
    layer quieter.
    """
    raws = bench_raws()
    ex = build_vocab(raws)["examples"]

    assert ex["task"] in {r["task"] for r in raws}
    assert ex["authority_basis"] in {a for r in raws for a in r.get("authority_basis") or []}
    assert ex["documents"] in {d["path"] for r in raws for d in r.get("documents") or []}

    # A placeholder is truncated rather than wrapped, so the shortest task wins.
    assert len(ex["task"]) == min(len(r["task"]) for r in raws if r.get("task"))
    # And the authority example carries an article number — the part a drafter
    # is most likely to leave out.
    assert any(ch.isdigit() for ch in ex["authority_basis"]), ex


def test_vocab_examples_survive_an_empty_set() -> None:
    """No items, no examples: the form falls back to its own format templates."""
    assert build_vocab([])["examples"] == {"task": "", "authority_basis": "", "documents": ""}


def test_vocab_numbers_each_family_from_the_set() -> None:
    vocab = build_vocab(bench_raws())
    by_prefix = {e["prefix"]: e for e in vocab["id_prefixes"]}
    assert set(by_prefix) == {"core-lit-", "core-tx-", "ret-", "wf-"}

    for prefix, entry in by_prefix.items():
        numbers = sorted(int(e[len(prefix):]) for e in entry["examples"])
        width = len(entry["examples"][0]) - len(prefix)
        assert entry["count"] == len(numbers)
        assert entry["next"] == prefix + str(max(numbers) + 1).zfill(width)
        assert entry["next"] not in entry["examples"]

    # Track and category are recorded because neither is in the string, and they
    # are what let a new item be numbered like the ones it resembles.
    assert by_prefix["core-tx-"]["tracks"] == ["core"]
    assert by_prefix["core-tx-"]["categories"] == ["Transaction"]
    assert by_prefix["wf-"]["tracks"] == ["workflows"]


def test_next_id_prefers_the_family_the_item_resembles() -> None:
    vocab = build_vocab(bench_raws())
    assert next_id(vocab, track="core", category="Transaction") == "core-tx-0003"
    assert next_id(vocab, track="core", category="Litigation") == "core-lit-0006"
    assert next_id(vocab, track="workflows") == "wf-0009"
    assert next_id(vocab, track="retrieval") == "ret-0011"

    # An explicit prefix wins over the narrowing.
    assert next_id(vocab, prefix="wf-", track="core") == "wf-0009"

    # Unknown prefix, unknown track, empty set: never somebody else's number.
    assert next_id(vocab, prefix="new-") == "new-" + str(1).zfill(DEFAULT_WIDTH)
    assert next_id({}, prefix="x-") == "x-0001"
    assert next_id({}, track="core") == ""
    assert next_id({}) == ""


def test_vocab_ignores_items_with_no_usable_number() -> None:
    vocab = build_vocab([
        {"id": "draft", "track": "core", "category": ""},
        {"id": "", "track": "core"},
    ])
    assert vocab["id_prefixes"] == []
    assert next_id(vocab) == ""


def test_items_json_carries_the_package_s_derivation() -> None:
    """The page reads `vocab` from items.json; a stale copy is a suggestion list
    that disagrees with the set it claims to describe."""
    from tools.build_items_index import build

    assert ITEMS_JSON.is_file(), "run: python tools/build_items_index.py"
    committed = json.loads(ITEMS_JSON.read_text(encoding="utf-8"))
    assert committed == build(BENCH)
    assert committed["vocab"] == build_vocab(bench_raws())
    assert "vocab" in committed
