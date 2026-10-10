"""LLM helper (B1): prompt + JSON schema in, validated JSON out.

- Model and key come from .env (LLM_MODEL=<provider>/<model> plus that
  provider's key, e.g. gemini/... + GEMINI_API_KEY; see .env.example).
- Responses are cached on disk in .cache/llm/, so the same prompt is free.
- llm_calls() counts real (non-cached) API calls for the evaluation.
- If no key is configured, or LLM_OFFLINE=1, ask_json() returns None and the
  caller uses its deterministic fallback. The demo never dies on the network.
"""

from __future__ import annotations

import hashlib
import json
import os
import threading
from pathlib import Path
from typing import TypeVar

from dotenv import load_dotenv
from pydantic import BaseModel, ValidationError

ROOT = Path(__file__).resolve().parent.parent
CACHE_DIR = ROOT / ".cache" / "llm"
load_dotenv(ROOT / ".env")

T = TypeVar("T", bound=BaseModel)

_lock = threading.Lock()
_stats = {"calls": 0, "cache_hits": 0, "failures": 0}


def model_name() -> str:
    return os.getenv("LLM_MODEL", "")


# Which environment variable holds the key for each provider (same as scripts/check_llm.py).
KEY_FOR_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "ollama": None,  # local model, no key needed
}


def llm_available() -> bool:
    if os.getenv("LLM_OFFLINE") == "1":
        return False
    model = model_name()
    if not model or "REPLACE" in model or "/" not in model:
        return False
    key_name = KEY_FOR_PROVIDER.get(model.split("/", 1)[0])
    if key_name is None:
        return True
    key = os.getenv(key_name, "")
    return bool(key) and "REPLACE" not in key


def llm_calls() -> int:
    return _stats["calls"]


def llm_stats() -> dict[str, int]:
    return dict(_stats)


def _cache_path(key: str) -> Path:
    return CACHE_DIR / f"{hashlib.sha256(key.encode()).hexdigest()[:32]}.json"


def ask_json(prompt: str, schema: type[T], system: str = "", max_tokens: int = 400) -> T | None:
    """Return a validated `schema` instance, or None if the LLM is unavailable/failed."""
    if not llm_available():
        return None
    model = model_name()
    key = json.dumps([model, system, prompt, schema.model_json_schema()], sort_keys=True)
    path = _cache_path(key)
    if path.exists():
        try:
            out = schema.model_validate_json(path.read_text(encoding="utf-8"))
            with _lock:
                _stats["cache_hits"] += 1
            return out
        except ValidationError:
            path.unlink(missing_ok=True)

    from litellm import completion  # slow import, only when needed

    messages = []
    instructions = (
        "Reply with ONLY a JSON object matching this JSON schema, no prose:\n"
        + json.dumps(schema.model_json_schema())
    )
    messages.append({"role": "system", "content": (system + "\n\n" + instructions).strip()})
    messages.append({"role": "user", "content": prompt})

    for attempt in range(2):
        try:
            with _lock:
                _stats["calls"] += 1
            extra = {} if model.startswith("gemini/") else {"temperature": 0}  # Gemini 3 deprecates it
            resp = completion(
                model=model, messages=messages, max_tokens=max_tokens,
                response_format={"type": "json_object"}, timeout=30, **extra,
            )
            text = resp.choices[0].message.content or ""
            out = schema.model_validate_json(_strip_fences(text))
            CACHE_DIR.mkdir(parents=True, exist_ok=True)
            path.write_text(out.model_dump_json(), encoding="utf-8")
            return out
        except ValidationError as exc:
            messages.append({"role": "user", "content": f"That was invalid: {str(exc)[:300]}. Try again."})
        except Exception:  # noqa: BLE001 - network/provider errors -> fallback
            break
    with _lock:
        _stats["failures"] += 1
    return None


def _strip_fences(text: str) -> str:
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1] if "\n" in text else text
        text = text.rsplit("```", 1)[0]
    return text.strip()
