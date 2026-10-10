"""STAND-IN belief engine, runbook, validator and decision rule.

Placeholders for Person A's intelligence/ and simulator/ modules (A3, A5, A6)
so the agents and console run end to end now. The likelihoods are hand-set
from the fault signatures in the plan, not estimated from runs (that is A4).
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field

from shared.types import CORRECT_FIX, Action, Belief, Hypothesis, Level, uniform_belief

LEVELS = (Level.LOW, Level.MEDIUM, Level.HIGH)

# P(low, medium, high | role of the feature under a hypothesis)
PROFILE = {
    "normal": (0.85, 0.12, 0.03),
    "normal_high": (0.03, 0.12, 0.85),  # minutes_since_deploy is normally large
    "sig": (0.05, 0.20, 0.75),
    "sig_low": (0.75, 0.20, 0.05),
    "up": (0.10, 0.45, 0.45),
    "up_mod": (0.15, 0.60, 0.25),
}

SIGNATURES: dict[Hypothesis, dict[str, str]] = {
    Hypothesis.DB_FAULT: {
        "replication_lag_s": "sig", "slow_queries": "sig", "lock_waits": "sig",
        "payment_error_rate": "up", "queue_depth": "up", "latency_ms": "up",
    },
    Hypothesis.BAD_DEPLOY: {
        "minutes_since_deploy": "sig_low", "canary_error_rate": "sig",
        "payment_error_rate": "up", "edge_error_rate": "up", "config_changes": "up",
    },
    Hypothesis.ATTACK: {
        "traffic_anomaly": "sig", "failed_logins": "sig", "suspicious_sources": "sig",
        "request_rate": "sig", "upstream_timeouts": "up", "edge_error_rate": "up",
    },
    Hypothesis.DEPENDENCY_TIMEOUT: {
        "upstream_timeouts": "sig", "latency_ms": "sig", "queue_depth": "up",
        "payment_error_rate": "up_mod", "edge_error_rate": "up_mod",
        "downstream_p99_ms": "sig", "conn_pool_saturation": "sig",
    },
}


def likelihood(feature: str, level: Level, h: Hypothesis) -> float:
    role = SIGNATURES[h].get(feature)
    if role is None:
        role = "normal_high" if feature == "minutes_since_deploy" else "normal"
    return PROFILE[role][LEVELS.index(Level(level))]


def normalize(b: dict) -> Belief:
    total = sum(b.values()) or 1.0
    return {Hypothesis(h): v / total for h, v in b.items()}


class StandInBeliefEngine:
    def update(self, agent_id: str, belief: Belief, levels: dict[str, Level]) -> Belief:
        post = {h: belief.get(h, 0.0) for h in Hypothesis}
        for f, lvl in levels.items():
            for h in Hypothesis:
                post[h] *= likelihood(f, lvl, h)
        return normalize(post)


def failed_action_update(belief: Belief, action: Action, strength: float = 0.15) -> Belief:
    """'We tried X and it did not help' is evidence against what X fixes."""
    post = dict(belief)
    for h, fix in CORRECT_FIX.items():
        if fix == action:
            post[h] *= strength
    return normalize(post)


def log_pool(beliefs: list[Belief], weights: list[float] | None = None) -> Belief:
    weights = weights or [1.0] * len(beliefs)
    logp = {h: 0.0 for h in Hypothesis}
    for b, w in zip(beliefs, weights):
        for h in Hypothesis:
            logp[h] += w * math.log(max(b.get(h, 0.0), 1e-9))
    m = max(logp.values())
    return normalize({h: math.exp(v - m) for h, v in logp.items()})


def entropy(b: Belief) -> float:
    return -sum(p * math.log2(p) for p in b.values() if p > 0)


def brier(b: Belief, truth: Hypothesis) -> float:
    return sum((b.get(h, 0.0) - (1.0 if h == truth else 0.0)) ** 2 for h in Hypothesis)


# --------------------------------------------------------------------------
# Runbook (Mode A) - deliberately realistic, first matching rule wins
# --------------------------------------------------------------------------
@dataclass
class Rule:
    name: str
    action: Action
    when: str


RULES = [
    Rule("db_lag", Action.FAILOVER_DB, "replication_lag_s high AND slow_queries high"),
    Rule("traffic_spike", Action.BLOCK_TRAFFIC, "error spike AND traffic_anomaly high"),
    Rule("recent_deploy", Action.ROLLBACK_DEPLOY, "deploy < 15 min ago AND error spike"),
    Rule("upstream_timeouts", Action.RESTART_SERVICE, "upstream_timeouts high AND latency high"),
]


def runbook_matches(levels: dict[str, Level]) -> list[Rule]:
    hi = lambda f: levels.get(f) == Level.HIGH  # noqa: E731
    spike = hi("edge_error_rate") or hi("payment_error_rate")
    checks = {
        "db_lag": hi("replication_lag_s") and hi("slow_queries"),
        "traffic_spike": spike and hi("traffic_anomaly"),
        "recent_deploy": levels.get("minutes_since_deploy") == Level.LOW and spike,
        "upstream_timeouts": hi("upstream_timeouts") and hi("latency_ms"),
    }
    return [r for r in RULES if checks[r.name]]


# --------------------------------------------------------------------------
# Safety validator
# --------------------------------------------------------------------------
RISKY = {
    Action.FAILOVER_DB: "risks data consistency (replica may be behind)",
    Action.BLOCK_TRAFFIC: "can lock out real customers",
}
FAILOVER_HARD_LAG_S = 20.0


@dataclass
class Verdict:
    allowed: bool
    risky: bool
    reason: str


def validate(action: Action, state: dict[str, float], human_approved: bool = False) -> Verdict:
    if action == Action.FAILOVER_DB and state.get("replication_lag_s", 0) > FAILOVER_HARD_LAG_S:
        if not human_approved:
            return Verdict(False, True, f"replication lag {state['replication_lag_s']:.1f}s > {FAILOVER_HARD_LAG_S}s: consistency violation")
    if action in RISKY:
        return Verdict(True, True, RISKY[action])
    return Verdict(True, False, "safe")


# --------------------------------------------------------------------------
# Decision rule (act / probe / escalate) used by the Mode B aggregator
# --------------------------------------------------------------------------
ACT_THRESHOLD = 0.75
RISKY_ACT_THRESHOLD = 0.9
MAX_PROBES = 2


@dataclass
class Decision:
    kind: str  # "act" | "probe" | "escalate"
    action: Action
    confidence: float
    reason: str
    options: list[dict] = field(default_factory=list)


def decide(pooled: Belief, state: dict[str, float], probes_used: int) -> Decision:
    top = max(pooled, key=pooled.get)
    p = pooled[top]
    action = CORRECT_FIX[top]
    verdict = validate(action, state)
    needed = RISKY_ACT_THRESHOLD if verdict.risky else ACT_THRESHOLD
    if verdict.allowed and p >= needed:
        return Decision("act", action, p, f"P({top.value})={p:.2f} >= {needed} and validator: {verdict.reason}")
    if probes_used < MAX_PROBES:
        why = f"P({top.value})={p:.2f} < {needed}" if verdict.allowed else verdict.reason
        return Decision("probe", Action.PROBE, p, f"unsure ({why}); a cheap probe first")
    return Decision("escalate", action, p, f"still unsure after {probes_used} probes and the action is risky", escalation_options(pooled, state))


def escalation_options(pooled: Belief, state: dict[str, float]) -> list[dict]:
    opts = []
    for h, p in sorted(pooled.items(), key=lambda kv: -kv[1])[:3]:
        a = CORRECT_FIX[h]
        v = validate(a, state)
        opts.append({"action": a.value, "hypothesis": h.value, "probability": round(p, 3),
                     "risk": v.reason, "blocked_without_approval": not v.allowed})
    opts.append({"action": Action.NOOP.value, "hypothesis": None, "probability": None,
                 "risk": "incident continues; errors keep hurting availability", "blocked_without_approval": False})
    return opts


__all__ = [
    "StandInBeliefEngine", "failed_action_update", "log_pool", "entropy", "brier",
    "runbook_matches", "validate", "decide", "escalation_options", "uniform_belief",
]
