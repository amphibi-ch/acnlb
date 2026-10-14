"""Cross-checks between the page, its scripts, its CSS data and the bundler.

There is no DOM here to test against — jsdom is not installable in this
environment — so these are the checks that stand in for one. They are the
mechanical half of "it renders": every element the scripts reach for by id must
exist in the HTML, and every download the page links to must be something the
bundler actually produces. A typo in either is a blank section or a 404 in
production and nothing in the console to explain it.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

SITE = ROOT / "site"
HTML = (SITE / "index.html").read_text(encoding="utf-8")
JS_FILES = ["app.js", "item-ui-placeholder", "item-form.js", "form-ui.js"]
JS_SOURCES = {n: (SITE / n).read_text(encoding="utf-8")
              for n in ("app.js", "item-form.js", "form-ui.js")}
CSS = (SITE / "styles.css").read_text(encoding="utf-8")


def strip_comments(src: str) -> str:
    """Comments are prose. Scanned naively, a comment about `schema.json` reads as
    a field access and a comment about a class reads as an unstyled one."""
    src = re.sub(r"/\*.*?\*/", "", src, flags=re.S)
    return re.sub(r"^\s*//.*$", "", src, flags=re.M)


JS_CODE = {n: strip_comments(s) for n, s in JS_SOURCES.items()}

# Ids the scripts look for defensively: absent means "feature off", not "bug".
OPTIONAL_IDS = {"row-template"}


def html_ids() -> set[str]:
    return set(re.findall(r'\bid="([^"]+)"', HTML))


def js_id_lookups() -> dict[str, set[str]]:
    found: dict[str, set[str]] = {}
    for name, src in JS_CODE.items():
        ids = set(re.findall(r'getElementById\(\s*"([^"]+)"\s*\)', src))
        ids |= set(re.findall(r'querySelector\(\s*"#([A-Za-z0-9_-]+)"\s*\)', src))
        found[name] = ids
    return found


def test_every_id_the_scripts_use_exists_in_the_html() -> None:
    known = html_ids() | OPTIONAL_IDS
    missing = {name: sorted(ids - known) for name, ids in js_id_lookups().items()}
    assert all(not v for v in missing.values()), f"ids referenced but not in index.html: {missing}"


def test_data_attributes_the_scripts_query_exist_in_the_html() -> None:
    """`[data-dl]` is how the download cards are found; a rename breaks them silently."""
    used = set()
    for src in JS_CODE.values():
        used |= set(re.findall(r'"(data-[a-z-]+)"', src))
        used |= set(re.findall(r'querySelectorAll\(\s*"\[(data-[a-z-]+)\]"', src))
    present = set(re.findall(r"\b(data-[a-z-]+)=", HTML))
    # Some are written by the scripts onto nodes they create.
    written_runtime = {"data-field"}
    assert used <= present | written_runtime, sorted(used - present - written_runtime)


def test_html_asset_references_resolve_inside_site() -> None:
    refs = re.findall(r'<script src="([^"]+)"', HTML)
    refs += re.findall(r'<link[^>]+href="([^"]+\.(?:css|js))"', HTML)
    assert refs, "index.html references no local script or stylesheet"
    for ref in refs:
        assert not ref.startswith(("http", "//", "data:")), ref
        assert (SITE / ref).is_file(), f"missing asset: {ref}"


def test_stamp_assets_covers_every_script() -> None:
    """A script the deploy does not stamp keeps yesterday's URL and yesterday's cache."""
    stamps = subprocess.run(
        [sys.executable, str(ROOT / "tools" / "stamp_assets.py"), "--help"],
        capture_output=True, text=True, cwd=str(ROOT),
    )
    assert stamps.returncode == 0
    workflow = (ROOT / ".github" / "workflows" / "deploy-pages.yml").read_text(encoding="utf-8")
    for ref in re.findall(r'<script src="([^"]+)"', HTML):
        assert ref in workflow, f"{ref} is loaded by the page but not stamped by deploy-pages.yml"
    assert "styles.css" in workflow


def test_download_links_match_what_the_bundler_emits(tmp_path: Path) -> None:
    """The page's hrefs and the bundler's output names must be the same list.

    They are written in two places by necessity — the hrefs ship as static HTML so
    the links work before any fetch — so something has to compare them.
    """
    from tools.build_bundle import main as build_main

    out = tmp_path / "dl"
    argv = sys.argv
    sys.argv = ["build_bundle.py", "--items", "items/bench10", "--workspace", "--out", str(out)]
    try:
        assert build_main() == 0
    finally:
        sys.argv = argv

    linked = set(re.findall(r'href="download/([^"]+)"', HTML))
    produced = {p.name for p in out.iterdir()} - {"manifest.json", "HOWTO.txt"}
    assert linked == produced, f"page links {sorted(linked)}, bundler emits {sorted(produced)}"

    # And the download facts the page shows are read out of the manifest, so its
    # shape is part of the page's contract.
    manifest = json.loads((out / "manifest.json").read_text(encoding="utf-8"))
    assert {"generator", "schema_version", "commit", "bundles"} <= set(manifest)
    for bundle in manifest["bundles"]:
        assert {"name", "kind", "count", "total_points", "entry_count", "artifacts"} <= set(bundle)
        for artifact in bundle["artifacts"]:
            assert {"path", "bytes", "sha256"} == set(artifact)


def test_schema_exports_everything_the_form_reads() -> None:
    """site/schema.json is the form's only source of vocabulary — no re-typing."""
    schema = json.loads((SITE / "schema.json").read_text(encoding="utf-8"))
    assert set(schema) == {
        "schema_version",
        "required_fields",
        "valid_tracks",
        "track_labels",
        "valid_tiers",
        "tier_points",
        "retrieval_classes",
        "negatives",
        "default_rubric",
        "intake_sections",
        "gold_sections",
        "retrieval_sections",
        "paths",
        "id_pattern",
        "id_hint",
    }
    for key in ("paths", "tier_points", "track_labels"):
        assert schema[key], key

    # `(?<!")` keeps the filename literal `"schema.json"` out of the match.
    used = set(re.findall(r'(?<!")schema\.([a-z_]+)', JS_CODE["item-form.js"]))
    used |= set(re.findall(r'(?<!")SCHEMA\.([a-z_]+)', JS_CODE["form-ui.js"]))
    unknown = {u for u in used if u not in schema}
    assert not unknown, f"scripts read schema fields that are not exported: {sorted(unknown)}"
    assert used, "no schema field reads found — did the accessor change?"


def test_rubric_skeleton_and_taxonomy_are_not_hardcoded() -> None:
    """The page must fetch the vocabulary, not embed a copy of it.

    `HALLUC_FACT` is allowed: rubric.py falls back to it when a negative line
    carries no `[CODE]`, and item-form.js mirrors that fallback. The skeleton and
    the rest of the taxonomy are not.
    """
    for name, src in JS_CODE.items():
        assert "Affirmative Points" not in src, name
        assert "REPEALED_LAW" not in src, name
        assert "WRONG_HIERARCHY" not in src, name


def _balanced(src: str, start: int) -> str:
    """Text between the bracket at `start` and its match, string literals respected."""
    depth = 0
    quote = None
    i = start
    while i < len(src):
        ch = src[i]
        if quote:
            if ch == "\\":
                i += 2
                continue
            if ch == quote:
                quote = None
        elif ch in "\"'":
            quote = ch
        elif ch == "(":
            depth += 1
        elif ch == ")":
            depth -= 1
            if depth == 0:
                return src[start + 1:i]
        i += 1
    return ""


def _split_top_level(text: str) -> list[str]:
    parts, depth, quote, buf = [], 0, None, []
    for ch in text:
        if quote:
            buf.append(ch)
            if ch == quote:
                quote = None
            continue
        if ch in "\"'":
            quote = ch
        elif ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        elif ch == "," and depth == 0:
            parts.append("".join(buf))
            buf = []
            continue
        buf.append(ch)
    parts.append("".join(buf))
    return [p.strip() for p in parts]


def _quoted(text: str) -> list[str]:
    return re.findall(r'"([^"\n]*)"', text)


def class_literals(src: str) -> set[str]:
    """Class names the script assigns, read from class positions only.

    Scanning every string literal would drag in element ids, `data-` attribute
    names and filenames; the whole point is to catch a class with no rule.
    """
    tokens: set[str] = set()
    for m in re.finditer(r"\bel\(", src):
        args = _split_top_level(_balanced(src, m.end() - 1))
        if len(args) >= 2:
            for literal in _quoted(args[1]):
                tokens.update(literal.split())
    for m in re.finditer(r"\.className\s*=\s*", src):
        end = src.find(";", m.end())
        for literal in _quoted(src[m.end():end]):
            tokens.update(literal.split())
    return {t for t in tokens if re.fullmatch(r"[a-z][a-z0-9-]*", t)}


def test_css_defines_the_classes_the_scripts_assign() -> None:
    """A class with no rule is an unstyled block, which reads as a layout bug."""
    css_classes = set(re.findall(r"\.([a-z][a-z0-9-]*)\b", CSS))
    offenders = set()
    for src in JS_CODE.values():
        offenders |= class_literals(src) - css_classes
    assert not offenders, f"classes assigned in JS with no CSS rule: {sorted(offenders)}"
    assert class_literals(JS_CODE["form-ui.js"]), "scanner found no classes — did the syntax change?"


def test_language_dicts_have_the_same_keys() -> None:
    """Two hand-written dictionaries, so a missing key is one click from blank text."""
    checked = 0
    for name, source in JS_CODE.items():
        block = re.search(r"var T = \{(.*?)\n  \};", source, re.S)
        if not block:
            continue
        checked += 1
        keys = {}
        for key, body in re.findall(r"\n    (en|zh): \{(.*?)\n    \}", block.group(1), re.S):
            keys[key] = set(re.findall(r"^\s{6}([A-Za-z_][A-Za-z0-9_]*):", body, re.M))
        assert set(keys) == {"en", "zh"}, (name, set(keys))
        assert keys["en"] == keys["zh"], (name, sorted(keys["en"] ^ keys["zh"]))
    assert checked >= 2, "expected a translation table in app.js and form-ui.js"
