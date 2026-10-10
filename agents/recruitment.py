"""Capability-based team selection and mid-incident recruitment (B7).

Every selection is explained (capability match + the evidence that triggered
it) and logged to the ledger as a RECRUIT message.
"""

from __future__ import annotations

from agents.agent_base import AgentSpec, find_by_capability, load_registry
from shared.types import Belief, Hypothesis, Level

# Which capability is needed to rule a hypothesis in or out.
HYPOTHESIS_CAPABILITY = {
    Hypothesis.DB_FAULT: "database_analysis",
    Hypothesis.BAD_DEPLOY: "deploy_analysis",
    Hypothesis.ATTACK: "threat_detection",
    Hypothesis.DEPENDENCY_TIMEOUT: "dependency_timeout_analysis",
}
SYMPTOM_CAPABILITY = {"edge": "edge_traffic_analysis", "payments": "payment_flow_analysis"}

RECRUIT_BELIEF = 0.30  # mean P(dependency_timeout) that triggers a specialist
NO_ONE_CONFIDENT = 0.55  # ...or nobody's top hypothesis is above this


def select_initial_team(levels: dict[str, Level]) -> list[tuple[AgentSpec, str]]:
    """Pick the core team by capability, and say why each one was chosen."""
    reg = load_registry()
    chosen: list[tuple[AgentSpec, str]] = []
    for spec in reg.values():
        if not spec.core:
            continue
        abnormal = [f for f in spec.features if _abnormal(f, levels.get(f))]
        caps = ", ".join(spec.capabilities)
        rules_out = [h.value for h, c in HYPOTHESIS_CAPABILITY.items() if c in spec.capabilities]
        if abnormal:
            why = f"capability [{caps}] covers abnormal signals: {', '.join(abnormal)}"
        elif rules_out:
            why = f"capability [{caps}] needed to confirm or rule out {', '.join(rules_out)} (its signals look normal)"
        else:
            why = f"capability [{caps}] watches customer-facing symptoms"
        chosen.append((spec, why))
    return chosen


def recruitment_needed(beliefs: list[Belief], team_ids: set[str]) -> tuple[AgentSpec, str] | None:
    if not beliefs:
        return None
    mean_dep = sum(b.get(Hypothesis.DEPENDENCY_TIMEOUT, 0) for b in beliefs) / len(beliefs)
    best_conf = max(max(b.values()) for b in beliefs)
    trigger = None
    if mean_dep >= RECRUIT_BELIEF:
        trigger = f"team's mean P(dependency_timeout) = {mean_dep:.2f} >= {RECRUIT_BELIEF}"
    elif best_conf < NO_ONE_CONFIDENT:
        trigger = f"no agent is confident (best = {best_conf:.2f} < {NO_ONE_CONFIDENT})"
    if trigger is None:
        return None
    for spec in find_by_capability(HYPOTHESIS_CAPABILITY[Hypothesis.DEPENDENCY_TIMEOUT]):
        if spec.id not in team_ids:
            return spec, f"{trigger}; registry lookup for capability 'dependency_timeout_analysis' matched {spec.name}"
    return None


def _abnormal(feature: str, level: Level | None) -> bool:
    if level is None:
        return False
    if feature == "minutes_since_deploy":
        return level == Level.LOW
    return level != Level.LOW
