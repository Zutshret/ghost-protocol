"""Voice: the LLM writes what agents SAY; the code decides what they DO.

Everything an agent says in the ledger (challenges, the aggregator's explanation,
the briefing a human reads before approving, the end-of-run summary) can be
rewritten in natural language by the LLM. Four safeguards keep it harmless:

1. The LLM only ever returns a sentence. Actions, beliefs, votes and escalations
   are decided by code (belief engine, cost rule, validator) before the LLM is asked.
2. It is called only at decision points, never every tick, and answers are cached.
3. Its text is rejected (and the plain template used instead) if it
     - invents a number that is not in the facts we gave it,
     - names a cause or action that is not in the facts, or
     - is empty or too long.
4. If there is no key, no network, or the call fails: the template is used.
   The demo never depends on the LLM.
"""

from __future__ import annotations

import json
import re
import threading
from typing import Any

from pydantic import BaseModel, Field

from agents.llm import ask_json, llm_available
from shared.types import Action, Hypothesis

MAX_WORDS = 70

_lock = threading.Lock()
_stats = {"llm": 0, "template": 0, "rejected": 0}


def voice_stats() -> dict[str, int]:
    """How many lines came from the LLM, from templates, and how many LLM lines were rejected."""
    return dict(_stats)


class Line(BaseModel):
    text: str = Field(description="what you would say, 1 to 3 plain-English sentences, no markdown")


SYSTEM = (
    "You are {speaker} in an incident-response team for a payments platform. {role} {goal}"
    "Write ONLY what you would say out loud: plain English, no markdown, no lists. "
    "Use only the facts you are given. Never invent numbers, causes or actions. Write every number as digits (60%, 7 ticks), never as words."
)

TASKS = {
    "challenge": (
        "You disagree with a colleague and want to challenge them. Say what you believe and why, "
        "citing your evidence, and ask for theirs. 1 or 2 sentences."
    ),
    "aggregator": (
        "You are the aggregator. Explain to the team, in 2 sentences, what the pooled evidence says "
        "and why you chose this decision (act, probe, or ask a human). Keep every percentage you state."
    ),
    "briefing": (
        "Brief a busy human operator who must approve or reject. In 3 sentences: what we know and how "
        "sure we are, the leading options with their risks, and why you are asking instead of acting."
    ),
    "summary": (
        "Write a 3 sentence post-incident summary for the log: what the real cause was, what the team "
        "did, and how it turned out."
    ),
}


def _normalise(s: str) -> str:
    return re.sub(r"\s+", " ", s.lower().replace("_", " ")).strip()


def _numbers(s: str) -> set[str]:
    return {n.rstrip("0").rstrip(".") if "." in n else n for n in re.findall(r"\d+(?:\.\d+)?", s)}


def faithful(text: str, facts: dict[str, Any], *, allow_causes: bool = False) -> bool:
    """True if the text only uses numbers, causes and actions that appear in the facts.

    `allow_causes=True` is for an agent's own reading of its signals ("this points to
    db_fault"): naming a cause is its job, so only numbers and actions are checked.
    Whether that cause is right is decided by the belief engine, never by this text.
    """
    if not text or len(text.split()) > MAX_WORDS:
        return False
    blob = json.dumps(facts, default=str)
    if not _numbers(text) <= _numbers(blob):
        return False
    allowed, said = _normalise(blob), _normalise(text)
    terms = [_normalise(a.value) for a in Action]
    if not allow_causes:
        terms += [_normalise(h.value) for h in Hypothesis]
    return all(t in allowed for t in terms if t in said)


def clean(text: str) -> str:
    return re.sub(r"\s+", " ", text.replace("*", "").replace("`", "")).strip().strip('"')


def say(
    kind: str,
    facts: dict[str, Any],
    fallback: str,
    *,
    use_llm: bool = True,
    speaker: str = "the team",
    role: str = "",
    goal: str = "",
) -> str:
    """Return what to say: the LLM's wording if it is available and faithful, else `fallback`."""
    if not use_llm or kind not in TASKS or not llm_available():
        return _template(fallback)
    prompt = f"{TASKS[kind]}\n\nFacts (use only these):\n{json.dumps(facts, indent=1, default=str)}"
    system = SYSTEM.format(speaker=speaker, role=(role + " ") if role else "", goal=(f"Your goal: {goal} " if goal else ""))
    out = ask_json(prompt, Line, system=system, max_tokens=250)
    text = clean(out.text) if out is not None else ""
    if out is not None and not faithful(text, facts):
        with _lock:
            _stats["rejected"] += 1
        return _template(fallback)
    if not text:
        return _template(fallback)
    with _lock:
        _stats["llm"] += 1
    return text


def count_rejected() -> None:
    """Record an LLM line that failed the guard somewhere outside `say` (e.g. evidence rationales)."""
    with _lock:
        _stats["rejected"] += 1


def _template(fallback: str) -> str:
    with _lock:
        _stats["template"] += 1
    return fallback
