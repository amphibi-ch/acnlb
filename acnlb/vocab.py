"""The vocabulary a drafter should be choosing from, derived from an item set.

Nothing in the schema constrains ``category``, ``task_type``, ``jurisdiction``,
``authority_basis`` or a document path: they are free strings, deliberately, so
the set can grow a category nobody anticipated. But a free-text field with no
examples is how a set acquires 「合同审查」/「合同审核」/「contract review」 as three
task types — after which no report can group by task type, and nothing fails
loudly enough to notice.

So this is not a constraint, it is the answer to "what do the items that already
exist put here". It is *derived*, never hand-typed, and every writer reads the
same derivation:

* ``tools/build_items_index.py`` publishes it to the site as ``items.json.vocab``,
  which the web form offers as dropdown options and uses for its placeholders
  (``vocab.examples``);
* ``tools/issue_to_intake.py`` uses it to assign the next free id when a
  contributor opening an issue leaves the id blank.

That is the point of putting it here rather than in either caller: a second
derivation is a second thing to drift, and the failure would be a form
suggesting a task type the published set has never used.
"""

from __future__ import annotations

import re
from collections.abc import Iterable, Sequence
from typing import Any

# `core-lit-0003` → prefix `core-lit-`, number 0003. Anything else (an id with no
# trailing number) is left alone: it has no "next".
_ID_NUMBER = re.compile(r"^(?P<prefix>.*?)(?P<number>\d+)$")

# Ids in this set are padded to four digits. A prefix seen for the first time has
# no observed width, so assume the same convention rather than emitting `x-1`.
DEFAULT_WIDTH = 4


def _unique_in_order(values: Iterable[str]) -> list[str]:
    """Deduplicate, keeping the first occurrence — frequency order, not alphabetical.

    The lists are meant to be read by someone deciding what to type, and the
    first entry should be a common answer, not one that happens to sort first.
    """
    seen: dict[str, None] = {}
    for v in values:
        v = (v or "").strip()
        if v:
            seen.setdefault(v, None)
    return list(seen)


def _authority_entries(items: Sequence[dict[str, Any]]) -> list[str]:
    return _unique_in_order(
        entry for item in items for entry in (item.get("authority_basis") or [])
    )


def _document_paths(items: Sequence[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for item in items:
        for doc in item.get("documents") or []:
            out.append(doc if isinstance(doc, str) else str(doc.get("path", "")))
    return _unique_in_order(out)


def _examples(items: Sequence[dict[str, Any]]) -> dict[str, str]:
    """One real value per field, for the form's placeholders.

    A placeholder is the cheapest documentation a field can carry, and the only
    honest one is a value the set already contains: `《民法典》第585条` teaches
    the house style — short title *and* article number, not one or the other —
    in a way "e.g. a citation" cannot. Hand-writing an example here is how the
    page would start suggesting a shape no item in the set has.

    The *shortest* task wins because a placeholder is truncated, not wrapped, and
    a full sentence would be cut mid-word in a single-line input. The authority
    prefers an entry carrying a number over the alphabetically first one, since
    the number is the part a drafter is most likely to omit.
    """
    tasks = _unique_in_order(item.get("task") or "" for item in items)
    authorities = _authority_entries(items)
    documents = _document_paths(items)
    cited = next((a for a in authorities if any(ch.isdigit() for ch in a)), "")
    return {
        "task": min(tasks, key=len) if tasks else "",
        "authority_basis": cited or (authorities[0] if authorities else ""),
        "documents": documents[0] if documents else "",
    }


def _id_prefixes(items: Sequence[dict[str, Any]]) -> list[dict[str, Any]]:
    """``[{prefix, next, count, tracks, categories, examples}]`` per prefix.

    Numbering is per prefix, so `core-lit-0005` being taken says nothing about
    `wf-`. Width is taken from the ids actually present, so a set that pads to
    three digits does not start emitting four. Track and category are recorded
    because neither is derivable from the string — `wf-0006` is a `workflows`
    item and `core-tx-0001` a `Transaction` one, and nothing in the text says so —
    and they are what lets a new item be numbered like the ones it resembles.
    """
    groups: dict[str, list[tuple[str, str, str]]] = {}
    for item in items:
        iid = (item.get("id") or "").strip()
        m = _ID_NUMBER.match(iid)
        if m:
            groups.setdefault(m.group("prefix"), []).append((
                m.group("number"),
                (item.get("track") or "").strip(),
                (item.get("category") or "").strip(),
            ))

    out: list[dict[str, Any]] = []
    for prefix in sorted(groups):
        triples = groups[prefix]
        width = max(len(n) for n, _, _ in triples)
        highest = max(int(n) for n, _, _ in triples)
        out.append({
            "prefix": prefix,
            "next": prefix + str(highest + 1).zfill(width),
            "count": len(triples),
            "tracks": sorted({t for _, t, _ in triples if t}),
            "categories": sorted({c for _, _, c in triples if c}),
            "examples": sorted(prefix + n for n, _, _ in triples),
        })
    return out


def next_id(
    vocab: dict[str, Any], prefix: str = "", track: str = "", category: str = ""
) -> str:
    """The next unused id, for the family the caller is describing.

    An explicit `prefix` wins. Otherwise narrow by track, then by category, and
    take the busiest family left: a new `Transaction` item is numbered
    `core-tx-…`, not `core-lit-…`, which is the difference between a suggestion
    someone accepts and one they have to correct. An unknown prefix gets `0001`
    rather than someone else's number — answering with a prefix the caller did
    not ask for is how an id ends up in the wrong family.

    Mirrored in `site/item-form.js` so the page's "next free id" button and the
    issue-to-PR tool cannot disagree about what that id is.
    """
    entries = [e for e in (vocab.get("id_prefixes") or []) if e.get("prefix")]
    if prefix:
        for e in entries:
            if e["prefix"] == prefix:
                return str(e.get("next") or "")
        return prefix + str(1).zfill(DEFAULT_WIDTH)

    pool = [e for e in entries if track and track in (e.get("tracks") or [])] or entries
    narrowed = [e for e in pool if category and category in (e.get("categories") or [])]
    if narrowed:
        pool = narrowed
    if not pool:
        return ""
    busiest = max(pool, key=lambda e: (e.get("count") or 0, str(e.get("prefix"))))
    return str(busiest.get("next") or "")


def build_vocab(items: Sequence[dict[str, Any]]) -> dict[str, Any]:
    """Derive the suggestion lists for a set of raw item dicts."""
    return {
        "categories": _unique_in_order(item.get("category") or "" for item in items),
        "task_types": _unique_in_order(item.get("task_type") or "" for item in items),
        "jurisdictions": _unique_in_order(item.get("jurisdiction") or "" for item in items),
        "authority_basis": _authority_entries(items),
        "documents": _document_paths(items),
        "id_prefixes": _id_prefixes(items),
        "examples": _examples(items),
    }
