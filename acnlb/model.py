"""OpenAI-compatible model client (design doc: provider-agnostic, HTTP only).

Configured from env or a YAML model config: ``base_url`` + ``api_key`` + ``model``.
No vendor is hardcoded. Keys are never logged, printed, or written: the client
redacts the key and any token-bearing ``base_url`` in every string it hands back.

Only the chat-completions shape is assumed (``POST {base_url}/chat/completions``
with ``{"model", "messages"}``), which every OpenAI-compatible endpoint speaks.
"""

from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from dataclasses import dataclass
from pathlib import Path

_REDACT_KEYS = re.compile(r"(sk-[A-Za-z0-9_\-]{4,}|[A-Za-z0-9_\-]{24,})")
_URL_TOKEN = re.compile(r"(?i)([?&](?:api[-_]?key|key|token|access_token)=)[^&\s]+")


def redact(text: str) -> str:
    """Remove anything that looks like a secret or a token-bearing URL."""
    if not text:
        return text
    text = _URL_TOKEN.sub(r"\1***", text)
    return _REDACT_KEYS.sub("***", text)


class ModelError(RuntimeError):
    pass


@dataclass
class ModelConfig:
    model: str
    base_url: str = "https://api.openai.com/v1"
    api_key: str = ""
    temperature: float = 0.0
    max_tokens: int = 4096
    timeout: int = 120
    name: str = ""

    @property
    def redacted_base_url(self) -> str:
        return redact(self.base_url)

    def describe(self) -> str:
        return f"{self.name or self.model} @ {self.redacted_base_url}"

    @classmethod
    def from_yaml(cls, path: str | Path, *, name: str | None = None) -> "ModelConfig":
        import yaml

        data = yaml.safe_load(Path(path).read_text(encoding="utf-8")) or {}
        entries = data.get("models", data)
        if isinstance(entries, list):
            if name is None:
                entry = entries[0]
            else:
                match = [e for e in entries if e.get("name") == name]
                if not match:
                    raise ModelError(f"no model named {name!r} in {path}")
                entry = match[0]
        elif isinstance(entries, dict):
            if "model" in entries:
                entry = entries
            elif name and name in entries:
                entry = entries[name]
            elif len(entries) == 1:
                entry = next(iter(entries.values()))
            else:
                raise ModelError(
                    f"{path} defines multiple models; pass --model-name one of "
                    f"{sorted(entries)}"
                )
        else:
            raise ModelError(f"unrecognised model config in {path}")

        # env overrides win; never require a key in the committed file
        api_key = os.environ.get(entry.get("api_key_env", "MODEL_API_KEY"), "") or entry.get("api_key", "")
        base_url = os.environ.get("MODEL_BASE_URL", "") or entry.get("base_url", "https://api.openai.com/v1")
        return cls(
            model=entry["model"],
            base_url=base_url,
            api_key=api_key,
            temperature=float(entry.get("temperature", 0.0)),
            max_tokens=int(entry.get("max_tokens", 4096)),
            timeout=int(entry.get("timeout", 120)),
            name=entry.get("name", entry["model"]),
        )


class ModelClient:
    """Minimal OpenAI-compatible chat client over urllib. No key ever leaves here."""

    def __init__(self, config: ModelConfig):
        self.config = config

    def _endpoint(self) -> str:
        return self.config.base_url.rstrip("/") + "/chat/completions"

    def generate(self, prompt: str, *, system: str | None = None) -> str:
        if not self.config.api_key:
            raise ModelError(
                "no API key configured; set MODEL_API_KEY or api_key_env in the model config"
            )
        messages = []
        if system:
            messages.append({"role": "system", "content": system})
        messages.append({"role": "user", "content": prompt})
        payload = json.dumps(
            {
                "model": self.config.model,
                "messages": messages,
                "temperature": self.config.temperature,
                "max_tokens": self.config.max_tokens,
            }
        ).encode("utf-8")

        req = urllib.request.Request(
            self._endpoint(),
            data=payload,
            method="POST",
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self.config.api_key}",
            },
        )
        try:
            with urllib.request.urlopen(req, timeout=self.config.timeout) as resp:
                body = json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as exc:
            detail = redact(exc.read().decode("utf-8", "replace")[:500])
            raise ModelError(f"HTTP {exc.code} from model endpoint: {detail}") from None
        except urllib.error.URLError as exc:
            raise ModelError(f"network error calling model: {redact(str(exc.reason))}") from None

        try:
            return body["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelError(f"unexpected response shape: {redact(json.dumps(body)[:300])}") from exc
