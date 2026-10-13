"""Run driver (design doc section 3.8).

    for each item:
        rendered = render(prompt, documents)
        response = cache.get(key) or model.generate(rendered); cache.put(...)
        verdicts = judge.score(response, rubric)         # manual file or llm
        score = Σ(affirmative hit) − Σ(negative), floored at 0
    report per-item AND per-track

Non-negotiables implemented here: version stamping, content-hashed generation
cache, and a per-track breakdown (never only the mean).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

from . import PROTOCOL_VERSION, SCHEMA_VERSION, __version__
from .cache import ResponseCache, cache_key
from .judge import (
    VALIDATION_NOTE,
    Verdicts,
    build_judge_prompt,
    parse_judge_output,
)
from .model import ModelClient, ModelConfig, redact
from .retrieval import RetrievalScore, combine, score_retrieval
from .rubric import parse_rubric_file
from .schema import Item
from .scorer import ItemScore, score


@dataclass
class ItemResult:
    item_id: str
    track: str
    task_type: str
    has_context: bool
    score: float
    max_positive_points: float
    raw_score: float
    negative_total: float
    affirmative_earned: float
    error: str | None = None
    verdict_source: str = "manual"
    judged_unvalidated: bool = False
    detail: dict = field(default_factory=dict)

    @property
    def pct(self) -> float:
        return 100.0 * self.score / self.max_positive_points if self.max_positive_points else 0.0


def render_prompt(item: Item, items_root: Path) -> str:
    """Compose the exact prompt handed to the model: item prompt + documents."""
    parts = [item.prompt.strip()]
    for doc in item.documents:
        dp = items_root / doc.path
        try:
            text = dp.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            text = f"[binary or unreadable document: {doc.path}]"
        parts.append(f"\n\n--- 附件：{doc.path} ---\n{text}")
    return "\n".join(parts)


@dataclass
class RunResult:
    run_id: str
    model: str
    base_url: str
    judge_mode: str
    items: list[ItemResult]
    started_at: str
    versions: dict
    notes: list[str] = field(default_factory=list)

    @property
    def scored_count(self) -> int:
        return sum(1 for r in self.items if r.error is None)

    def as_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "model": self.model,
            "base_url": self.base_url,
            "judge_mode": self.judge_mode,
            "started_at": self.started_at,
            "versions": self.versions,
            "scored_count": self.scored_count,
            "total_count": len(self.items),
            "notes": self.notes,
            "items": [
                {
                    "item_id": r.item_id,
                    "track": r.track,
                    "task_type": r.task_type,
                    "has_context": r.has_context,
                    "score": r.score,
                    "max_positive_points": r.max_positive_points,
                    "pct": round(r.pct, 2),
                    "raw_score": r.raw_score,
                    "negative_total": r.negative_total,
                    "error": r.error,
                    "verdict_source": r.verdict_source,
                    "judged_unvalidated": r.judged_unvalidated,
                    "detail": r.detail,
                }
                for r in self.items
            ],
        }


def _per_track(items: list[ItemResult]) -> dict[str, dict]:
    tracks: dict[str, dict] = {}
    for r in items:
        if r.error is not None:
            continue
        t = tracks.setdefault(r.track, {"n": 0, "earned": 0.0, "max": 0.0, "scores": []})
        t["n"] += 1
        t["earned"] += r.score
        t["max"] += r.max_positive_points
        t["scores"].append(r.pct)
    for t in tracks.values():
        t["pct"] = round(100.0 * t["earned"] / t["max"], 2) if t["max"] else 0.0
        t["earned"] = round(t["earned"], 6)
        t["max"] = round(t["max"], 6)
    return tracks


def per_track(run: RunResult) -> dict[str, dict]:
    return _per_track(run.items)


def run(
    items: list[Item],
    items_root: Path,
    *,
    model_config: ModelConfig,
    judge_mode: str = "manual",
    verdicts_dir: Path | None = None,
    responses_dir: Path | None = None,
    judge_client: ModelClient | None = None,
    run_id: str | None = None,
    cache_dir: Path | None = None,
    client: ModelClient | None = None,
    limit: int | None = None,
) -> RunResult:
    started = datetime.now(timezone.utc).isoformat(timespec="seconds")
    run_id = run_id or f"run-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}"
    cache = ResponseCache(cache_dir or (items_root.parent / "runs" / "_cache"))
    # A responses dir scores frozen text with no model call at all (no key, no
    # network) — used for re-scoring and for CI runs against fixtures.
    client = None if responses_dir else (client or ModelClient(model_config))
    results: list[ItemResult] = []
    notes: list[str] = []

    if judge_mode == "llm":
        notes.append(VALIDATION_NOTE)
    if responses_dir:
        notes.append(f"scored from frozen responses in {responses_dir} (no model call)")

    selected = items[:limit] if limit else items
    for item in selected:
        rubric_path = items_root / item.rubric
        try:
            rubric = parse_rubric_file(rubric_path)
        except Exception as exc:  # noqa: BLE001
            results.append(_err(item, f"rubric parse error: {exc}"))
            continue

        rendered = render_prompt(item, items_root)
        key = cache_key(item.id, model_config.model, rendered)

        try:
            if responses_dir:
                rpath = _find_response(responses_dir, item.id)
                if rpath is None:
                    raise FileNotFoundError(f"no frozen response for {item.id} in {responses_dir}")
                response = rpath.read_text(encoding="utf-8")
                cache.put(key, item_id=item.id, model=model_config.model, response=response)
            else:
                response = cache.get(key)
                if response is None:
                    response = client.generate(rendered)
                    cache.put(key, item_id=item.id, model=model_config.model, response=response)
        except Exception as exc:  # noqa: BLE001
            results.append(_err(item, f"generation error: {redact(str(exc))}"))
            continue

        # ---- verdicts: human file, else llm judge ----
        unvalidated = False
        try:
            if judge_mode == "manual":
                vpath = (verdicts_dir / f"{item.id}.verdicts.json") if verdicts_dir else None
                if vpath and vpath.exists():
                    v = Verdicts.load(vpath)
                else:
                    v = Verdicts(item_id=item.id)  # empty = nothing hit
            elif judge_mode == "llm":
                if judge_client is None:
                    raise RuntimeError("judge_mode=llm requires a judge_client")
                gold_text = (items_root / item.gold_answer).read_text(encoding="utf-8")
                jp = build_judge_prompt(item, rubric, response, gold_text)
                raw = judge_client.generate(jp)
                v = parse_judge_output(item.id, raw, rubric, judge_client.config.model)
                unvalidated = True
            else:
                raise ValueError(f"unknown judge mode {judge_mode!r}")
        except Exception as exc:  # noqa: BLE001
            results.append(_err(item, f"judge error: {redact(str(exc))}"))
            continue

        iscore: ItemScore = score(
            rubric, affirmative=v.affirmative, negative=v.negative
        )
        iscore.track = item.track

        rdetail: dict = {}
        if item.retrieval_gold is not None:
            rscore: RetrievalScore = score_retrieval(
                item.id, item.retrieval_gold, response_text=response
            )
            combine(iscore, rscore)
            rdetail["retrieval"] = rscore.as_dict()

        results.append(
            ItemResult(
                item_id=item.id,
                track=item.track,
                task_type=item.task_type,
                has_context=item.has_context,
                score=iscore.score,
                max_positive_points=iscore.affirmative_max,
                raw_score=iscore.raw_score,
                negative_total=iscore.negative_total,
                affirmative_earned=iscore.affirmative_earned,
                verdict_source=v.source,
                judged_unvalidated=unvalidated,
                detail={
                    "affirmative": [
                        {"key": a.key, "hit": a.hit, "points": a.points}
                        for a in iscore.affirmative
                    ],
                    "negative": [
                        {"key": n.key, "code": n.code, "count": n.count,
                         "subtotal": n.subtotal}
                        for n in iscore.negative
                    ],
                    **rdetail,
                },
            )
        )

    return RunResult(
        run_id=run_id,
        model=model_config.model,
        base_url=model_config.redacted_base_url,
        judge_mode=judge_mode,
        items=results,
        started_at=started,
        versions={
            "acnlb": __version__,
            "protocol": PROTOCOL_VERSION,
            "schema": SCHEMA_VERSION,
            "judge_mode": judge_mode,
            "judge_model": (judge_client.config.model if judge_client else ""),
            "model_config": model_config.name,
        },
        notes=notes,
    )


def _find_response(responses_dir: Path, item_id: str) -> Path | None:
    """Locate a frozen response for ``item_id``: <id>.txt / .good.txt / .json."""
    for name in (f"{item_id}.txt", f"{item_id}.good.txt", f"{item_id}.response.txt",
                 f"{item_id}.response.json", f"{item_id}.json"):
        p = responses_dir / name
        if p.exists():
            return p
    return None


def _err(item: Item, msg: str) -> ItemResult:
    return ItemResult(
        item_id=item.id,
        track=item.track,
        task_type=item.task_type,
        has_context=item.has_context,
        score=0.0,
        max_positive_points=item.max_positive_points,
        raw_score=0.0,
        negative_total=0.0,
        affirmative_earned=0.0,
        error=msg,
    )


def write_run(run_result: RunResult, out_dir: Path) -> Path:
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    payload = run_result.as_dict()
    payload["per_track"] = per_track(run_result)
    (out_dir / "results.json").write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    return out_dir / "results.json"


def bootstrap_ci(scores: list[float], *, n: int = 2000, seed: int = 0) -> tuple[float, float]:
    """95% bootstrap CI over item percentages (design doc section 3.8).

    Deterministic for a fixed seed so run reports are reproducible.
    """
    import random

    if not scores:
        return 0.0, 0.0
    rng = random.Random(seed)
    means = []
    k = len(scores)
    for _ in range(n):
        sample = [scores[rng.randrange(k)] for _ in range(k)]
        means.append(sum(sample) / k)
    means.sort()
    lo = means[int(0.025 * n)]
    hi = means[int(0.975 * n)]
    return round(lo, 2), round(hi, 2)
