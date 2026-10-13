"""Generation cache (design doc section 3.8).

Cache key = sha256(item_id, model, rendered_prompt). Re-scoring after a rubric
tweak therefore needs no new inference: the response is keyed on the prompt,
not the rubric. Cache lives under ``runs/_cache/`` and is gitignored.
"""

from __future__ import annotations

import hashlib
import json
from pathlib import Path


def cache_key(item_id: str, model: str, rendered_prompt: str) -> str:
    h = hashlib.sha256()
    h.update(item_id.encode("utf-8"))
    h.update(b"\x00")
    h.update(model.encode("utf-8"))
    h.update(b"\x00")
    h.update(rendered_prompt.encode("utf-8"))
    return h.hexdigest()


class ResponseCache:
    def __init__(self, root: str | Path):
        self.root = Path(root)
        self.root.mkdir(parents=True, exist_ok=True)

    def _path(self, key: str) -> Path:
        return self.root / f"{key}.json"

    def get(self, key: str) -> str | None:
        p = self._path(key)
        if not p.exists():
            return None
        return json.loads(p.read_text(encoding="utf-8"))["response"]

    def put(self, key: str, *, item_id: str, model: str, response: str) -> None:
        self._path(key).write_text(
            json.dumps(
                {"item_id": item_id, "model": model, "response": response},
                ensure_ascii=False,
                indent=2,
            ),
            encoding="utf-8",
        )
