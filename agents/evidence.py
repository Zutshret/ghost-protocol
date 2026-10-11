"""Evidence extraction and rationale (B4).

The LLM reads an agent's raw log lines and returns feature levels plus a short
plain-English reason. It never produces probabilities: those come from the
belief engine. If the LLM is off or returns a feature level that contradicts
the measured number, the measured level wins and the mismatch is recorded.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from agents import voice
from agents.llm import ask_json
from shared.types import FEATURE_BASELINES, Level, Observation

try:
    from standins.sim import EXTRA_BASELINES, THRESHOLDS
except ImportError:  # pragma: no cover
    EXTRA_BASELINES, THRESHOLDS = {}, {}

BASELINES = {**FEATURE_BASELINES, **EXTRA_BASELINES}


class Extraction(BaseModel):
    levels: dict[str, Literal["low", "medium", "high"]] = Field(
        description="feature name -> level, one entry per feature in the logs"
    )
    rationale: str = Field(description="one or two sentences, plain English, max 40 words")


SYSTEM = (
    "You are the {name} in an incident-response team for a payments platform. "
    "Your role: {role}. Your goal: {goal}. You only see your own telemetry."
)


def _threshold_text(features: list[str]) -> str:
    rows = []
    for f in features:
        med, high = THRESHOLDS.get(f, (None, None))
        base = BASELINES.get(f)
        if med is not None:
            rows.append(f"- {f}: baseline {base:g}; low < {med:g} <= medium < {high:g} <= high")
    return "\n".join(rows)


def extract(spec, obs: Observation, use_llm: bool) -> tuple[dict[str, Level], str, dict]:
    """Return (levels, rationale, info). info says where the levels came from."""
    measured = dict(obs.levels)
    info = {"source": "measured", "llm_disagreed": []}
    if use_llm and obs.logs:
        prompt = (
            "Log lines from your telemetry:\n" + "\n".join(obs.logs)
            + "\n\nLevel rules:\n" + _threshold_text(list(measured))
            + "\n\nClassify each feature as low/medium/high and say in one or two "
            "sentences what these signals suggest about the root cause "
            "(bad_deploy, attack, db_fault, dependency_timeout). Quote numbers exactly as they "
            "appear in the logs, invent no other numbers, and do not recommend actions."
        )
        out = ask_json(prompt, Extraction, system=SYSTEM.format(name=spec.name, role=spec.role, goal=spec.goal))
        if out is not None:
            levels = {}
            for f, lvl in measured.items():
                got = out.levels.get(f)
                if got is not None and Level(got) != lvl:
                    info["llm_disagreed"].append(f)
                levels[f] = lvl  # the number is ground truth for what the agent saw
            # The rationale is free text a human will read, so it gets the same guard as
            # the voice layer: no number that is not in the agent's own readings, and no
            # action name. If it fails, the plain measured-numbers sentence is used.
            text = voice.clean(out.rationale)
            facts = {"logs": obs.logs, "values": obs.values, "levels": {f: l.value for f, l in measured.items()},
                     "level_rules": _threshold_text(list(measured))}
            if voice.faithful(text, facts, allow_causes=True):
                info["source"] = "llm"
                return levels, text, info
            info["rationale_rejected"] = True
            voice.count_rejected()
            return levels, fallback_rationale(obs, measured), info
    return measured, fallback_rationale(obs, measured), info


def fallback_rationale(obs: Observation, levels: dict[str, Level]) -> str:
    notable = [f"{f}={obs.values[f]:g} is {lvl.value.upper()}" for f, lvl in levels.items()
               if (lvl != Level.LOW) != (f == "minutes_since_deploy")]
    if not notable:
        return "Everything I can see is near baseline."
    return "I see " + ", ".join(notable) + "."
