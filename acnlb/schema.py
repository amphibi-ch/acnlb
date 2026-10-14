"""Item schema (design doc section 3.3) — dataclasses + JSON validation.

One item is one JSON file under an items directory. The shape is exactly the
one in the design doc; we add a ``retrieval_gold`` block (optional, retrieval
track only) for the section 2.6 graded-relevance path. Nothing else is added,
and no second format is invented.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import SCHEMA_VERSION

REQUIRED_FIELDS = (
    "id",
    "track",
    "category",
    "task_type",
    "task",
    "prompt",
    "has_context",
    "jurisdiction",
    "authority_basis",
    "gold_answer",
    "rubric",
    "max_positive_points",
    "notes",
)

VALID_TRACKS = frozenset({"core", "workflows", "retrieval"})
VALID_TIERS = frozenset({"高", "中", "低"})

# Display labels for the three tracks. They live next to VALID_TRACKS because
# three different consumers need them (the site index, the download manifest and
# the web form); a second copy is a second thing to forget.
TRACK_LABELS: dict[str, str] = {
    "core": "核心",
    "workflows": "工作流",
    "retrieval": "检索",
}

# Graded-relevance tiers (section 2.6) and what each tier is worth by default.
# A rubric may override per item, but this is the number the form pre-fills.
DEFAULT_TIER_POINTS: dict[str, float] = {"高": 2.0, "中": 1.0, "低": 0.5}

# The gold-standard classes a retrieval item may declare (section 2.6). Not
# enforced by from_dict — it is a vocabulary, not a validation rule — but the web
# form offers exactly these so it cannot invent a fourth.
RETRIEVAL_CLASSES: tuple[str, ...] = ("statute", "similar_case", "document")


class SchemaError(ValueError):
    """An item file does not conform to the section 3.3 schema."""


@dataclass
class DocRef:
    path: str
    sha256: str | None = None

    @classmethod
    def from_dict(cls, d: Any) -> "DocRef":
        if isinstance(d, str):
            return cls(path=d)
        return cls(path=d["path"], sha256=d.get("sha256"))


@dataclass
class GoldItem:
    """One graded-relevance gold entry for a retrieval item (section 2.6)."""

    ref: str
    tier: str  # 高 / 中 / 低
    note: str = ""

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "GoldItem":
        tier = d["tier"]
        if tier not in VALID_TIERS:
            raise SchemaError(f"invalid relevance tier {tier!r}; use one of {sorted(VALID_TIERS)}")
        return cls(ref=d["ref"], tier=tier, note=d.get("note", ""))


@dataclass
class RetrievalGold:
    """Graded gold standard for a retrieval item."""

    klass: str  # one of RETRIEVAL_CLASSES
    gold_items: list[GoldItem]
    # tier -> points awarded when the response surfaces a gold item at that tier
    tier_points: dict[str, float] = field(
        default_factory=lambda: dict(DEFAULT_TIER_POINTS)
    )

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> "RetrievalGold":
        return cls(
            klass=d["class"],
            gold_items=[GoldItem.from_dict(g) for g in d["gold_items"]],
            tier_points=d.get("tier_points", dict(DEFAULT_TIER_POINTS)),
        )


@dataclass
class Item:
    id: str
    track: str
    category: str
    task_type: str
    task: str
    prompt: str
    documents: list[DocRef]
    has_context: bool
    jurisdiction: str
    authority_basis: list[str]
    gold_answer: str
    rubric: str
    max_positive_points: float
    notes: str
    retrieval_gold: RetrievalGold | None = None
    source_path: Path | None = None

    @property
    def is_synthetic(self) -> bool:
        return "SYNTHETIC" in self.notes.upper() or "合成" in self.notes

    def item_hash(self) -> str:
        """Stable hash of the scorable content of the item (identity + rubric ref)."""
        payload = json.dumps(
            {
                "id": self.id,
                "track": self.track,
                "prompt": self.prompt,
                "documents": [d.path for d in self.documents],
                "rubric": self.rubric,
            },
            ensure_ascii=False,
            sort_keys=True,
        )
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    @classmethod
    def from_dict(cls, d: dict[str, Any], source_path: Path | None = None) -> "Item":
        missing = [k for k in REQUIRED_FIELDS if k not in d]
        if missing:
            raise SchemaError(f"missing required field(s): {', '.join(missing)}")
        if d["track"] not in VALID_TRACKS:
            raise SchemaError(
                f"invalid track {d['track']!r}; one of {sorted(VALID_TRACKS)}"
            )
        if not isinstance(d["has_context"], bool):
            raise SchemaError("has_context must be a boolean")
        docs = [DocRef.from_dict(x) for x in d.get("documents", [])]
        if d["has_context"] and not docs:
            raise SchemaError("has_context is true but documents[] is empty")
        rg = d.get("retrieval_gold")
        if d["track"] == "retrieval" and not rg:
            raise SchemaError("retrieval items must carry a retrieval_gold block")
        if rg and d["track"] != "retrieval":
            raise SchemaError("retrieval_gold is only valid on the retrieval track")
        return cls(
            id=d["id"],
            track=d["track"],
            category=d["category"],
            task_type=d["task_type"],
            task=d["task"],
            prompt=d["prompt"],
            documents=docs,
            has_context=d["has_context"],
            jurisdiction=d["jurisdiction"],
            authority_basis=list(d["authority_basis"]),
            gold_answer=d["gold_answer"],
            rubric=d["rubric"],
            max_positive_points=float(d["max_positive_points"]),
            notes=d["notes"],
            retrieval_gold=RetrievalGold.from_dict(rg) if rg else None,
            source_path=source_path,
        )

    @staticmethod
    def load(path: Path) -> "Item":
        data = json.loads(Path(path).read_text(encoding="utf-8"))
        return Item.from_dict(data, source_path=Path(path))


def load_items(items_path: str | Path) -> list[Item]:
    """Load every item under ``items_path``.

    Accepts either a single ``.json`` item file or a directory. Directories are
    scanned for ``*.json`` (excluding ``rubric``/fixture helpers). Items are
    returned sorted by id so runs are reproducible.
    """
    p = Path(items_path)
    if p.is_file():
        return [Item.load(p)]
    if not p.is_dir():
        raise SchemaError(f"items path does not exist: {p}")
    items: list[Item] = []
    for f in sorted(p.glob("*.json")):
        if f.name.endswith(".rubric.json") or f.name.startswith("_"):
            continue
        items.append(Item.load(f))
    items.sort(key=lambda i: i.id)
    return items


def validate_item(item: Item, items_root: Path) -> list[str]:
    """Return a list of problems with ``item`` (empty = valid). Read-only.

    Checks cross-file references (documents, gold answer, rubric) resolve, and
    that the rubric's positive points equal ``max_positive_points``.
    """
    from .rubric import parse_rubric_file  # local import to avoid a cycle

    problems: list[str] = []
    root = Path(items_root)

    def resolve(rel: str) -> Path:
        return (root / rel).resolve()

    for doc in item.documents:
        dp = resolve(doc.path)
        if not dp.exists():
            problems.append(f"document not found: {doc.path}")
        elif doc.sha256:
            h = hashlib.sha256(dp.read_bytes()).hexdigest()
            if h != doc.sha256:
                problems.append(f"document sha256 mismatch: {doc.path}")

    gold = resolve(item.gold_answer)
    if not gold.exists():
        problems.append(f"gold answer not found: {item.gold_answer}")

    rubric_path = resolve(item.rubric)
    if not rubric_path.exists():
        problems.append(f"rubric not found: {item.rubric}")
    else:
        try:
            rubric = parse_rubric_file(rubric_path)
        except Exception as exc:  # noqa: BLE001 - surface any parse error
            problems.append(f"rubric parse error: {exc}")
        else:
            if abs(rubric.max_positive_points - item.max_positive_points) > 1e-9:
                problems.append(
                    "max_positive_points mismatch: item says "
                    f"{item.max_positive_points:g}, rubric sums to "
                    f"{rubric.max_positive_points:g}"
                )
            if rubric.item_id and rubric.item_id != item.id:
                problems.append(
                    f"rubric header id {rubric.item_id!r} != item id {item.id!r}"
                )
    return problems
