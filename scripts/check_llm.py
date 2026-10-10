"""Checks that your .env is set up and the LLM answers. Never prints your key.

Run:  uv run python scripts/check_llm.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"

# Which environment variable holds the key for each provider prefix.
KEY_FOR_PROVIDER = {
    "openai": "OPENAI_API_KEY",
    "anthropic": "ANTHROPIC_API_KEY",
    "gemini": "GEMINI_API_KEY",
    "groq": "GROQ_API_KEY",
    "ollama": None,  # local model, no key needed
}

if not env_path.exists():
    print("No .env file found. Copy .env.example to .env and fill it in.")
    sys.exit(1)

load_dotenv(env_path)

model = os.getenv("LLM_MODEL", "")
if not model or "REPLACE" in model or "/" not in model:
    print("Fix your .env: LLM_MODEL must look like provider/model-name, e.g. openai/<model>.")
    sys.exit(1)

provider = model.split("/", 1)[0]
if provider not in KEY_FOR_PROVIDER:
    print(f"Provider '{provider}' is not in this script's list; skipping the key check.")
    key_name = None
else:
    key_name = KEY_FOR_PROVIDER[provider]

if key_name:
    key = os.getenv(key_name, "")
    if not key or "REPLACE" in key:
        print(f"Fix your .env: {key_name} is not set.")
        sys.exit(1)
    print(f"API key found: yes (ends with ...{key[-4:]})")

print(f"Using model: {model}")

from litellm import completion  # imported late so errors above show quickly

try:
    response = completion(
        model=model,
        messages=[{"role": "user", "content": "Reply with exactly: GHOST PROTOCOL online"}],
        max_tokens=20,
    )
except Exception as exc:  # noqa: BLE001 - show any problem plainly
    print("The LLM call failed:")
    print(type(exc).__name__, str(exc)[:500])
    sys.exit(1)

print("LLM replied:", response.choices[0].message.content)
print("Setup OK.")
