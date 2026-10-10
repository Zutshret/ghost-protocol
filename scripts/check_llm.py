"""Checks that your .env is set up and the LLM answers. Never prints your key.

Run:  uv run python scripts/check_llm.py
"""

import os
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
env_path = ROOT / ".env"

if not env_path.exists():
    print("No .env file found. Copy .env.example to .env and fill it in.")
    sys.exit(1)

load_dotenv(env_path)

model = os.getenv("LLM_MODEL", "")
key = os.getenv("OPENAI_API_KEY", "")

problems = []
if not model or "REPLACE" in model:
    problems.append("LLM_MODEL is not set (use the form openai/<model-name>).")
if not key or "REPLACE" in key:
    problems.append("OPENAI_API_KEY is not set.")
if problems:
    print("Fix your .env:")
    for p in problems:
        print(" -", p)
    sys.exit(1)

print(f"Using model: {model}")
print(f"API key found: yes (ends with ...{key[-4:]})")

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
