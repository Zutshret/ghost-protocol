"""Shared types for GHOST PROTOCOL.

This file is the contract between Person A (simulator, intelligence, evaluation)
and Person B (agents, bus, console). Change it only after telling each other.
"""

from __future__ import annotations

from enum import Enum
from typing import Any, Callable, Protocol

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Core vocabulary
# --------------------------------------------------------------------------
class Hypothesis(str, Enum):
    """Possible root causes of an incident."""

    BAD_DEPLOY = "bad_deploy"
    ATTACK = "attack"
    DB_FAULT = "db_fault"
    DEPENDENCY_TIMEOUT = "dependency_timeout"


class Action(str, Enum):
    """Things the team can do to the system."""

    ROLLBACK_DEPLOY = "rollback_deploy"
    BLOCK_TRAFFIC = "block_traffic"  # can lock out real customers
    FAILOVER_DB = "failover_db"  # risks data consistency
    RESTART_SERVICE = "restart_service"
    PROBE = "probe"  # costs one tick, reveals one extra feature level
    NOOP = "noop"


class Level(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class Mode(str, Enum):
    """Ways of handling an incident (see the plan)."""

    A = "A"  # deterministic runbook only (baseline)
    B = "B"  # probabilistic agents + central aggregator (Level 2)
    C = "C"  # probabilistic agents, peer negotiation (Level 3)
    D = "D"  # hybrid: runbook first, agents only when needed


class ScenarioId(str, Enum):
    S1 = "S1"  # clear db_fault
    S2 = "S2"  # bad_deploy that looks like an attack
    S5 = "S5"  # ambiguous and high-stakes -> ask a human


SERVICES = ["gateway", "auth", "payments", "database", "cache"]

# Which action truly fixes which fault.
CORRECT_FIX: dict[Hypothesis, Action] = {
    Hypothesis.DB_FAULT: Action.FAILOVER_DB,
    Hypothesis.BAD_DEPLOY: Action.ROLLBACK_DEPLOY,
    Hypothesis.ATTACK: Action.BLOCK_TRAFFIC,
    Hypothesis.DEPENDENCY_TIMEOUT: Action.RESTART_SERVICE,
}


# --------------------------------------------------------------------------
# What each agent can see (partial observability)
# Healthy baseline values are in FEATURE_BASELINES.
# --------------------------------------------------------------------------
AGENT_FEATURES: dict[str, list[str]] = {
    "gateway": ["request_rate", "edge_error_rate", "upstream_timeouts"],
    "payments": ["payment_error_rate", "queue_depth", "latency_ms"],
    "database": ["replication_lag_s", "slow_queries", "lock_waits"],
    "security": ["traffic_anomaly", "failed_logins", "suspicious_sources"],
    "deployment": ["minutes_since_deploy", "canary_error_rate", "config_changes"],
}

AGENT_IDS = list(AGENT_FEATURES.keys())

FEATURE_BASELINES: dict[str, float] = {
    "request_rate": 100.0,
    "edge_error_rate": 0.01,
    "upstream_timeouts": 2.0,
    "payment_error_rate": 0.01,
    "queue_depth": 10.0,
    "latency_ms": 120.0,
    "replication_lag_s": 0.5,
    "slow_queries": 3.0,
    "lock_waits": 2.0,
    "traffic_anomaly": 0.1,
    "failed_logins": 5.0,
    "suspicious_sources": 1.0,
    "minutes_since_deploy": 600.0,
    "canary_error_rate": 0.01,
    "config_changes": 0.0,
}

# Later, if time allows: observability, auth, customer_impact, infrastructure,
# and a dynamically recruited "network_analyst".


# --------------------------------------------------------------------------
# Data passed around
# --------------------------------------------------------------------------
# A belief is a probability for each hypothesis. Values sum to 1.
Belief = dict[Hypothesis, float]


def uniform_belief() -> Belief:
    p = 1.0 / len(Hypothesis)
    return {h: p for h in Hypothesis}


class Observation(BaseModel):
    """What one agent sees at one tick. Only its own features are included."""

    agent_id: str
    tick: int
    values: dict[str, float]  # raw numbers
    levels: dict[str, Level]  # low / medium / high per feature
    logs: list[str] = Field(default_factory=list)  # raw log lines (LLM reads these)


class MessageType(str, Enum):
    TELEMETRY = "telemetry"
    BELIEF = "belief"
    EVIDENCE = "evidence"
    CHALLENGE = "challenge"
    PROPOSAL = "proposal"
    ACCEPT = "accept"
    REJECT = "reject"
    VETO = "veto"
    ESCALATE = "escalate"  # ask a human
    HUMAN_RESPONSE = "human_response"
    ACTION = "action"
    MODE_SWITCH = "mode_switch"  # runbook -> agents
    RECRUIT = "recruit"  # a specialist was selected from the registry


class Message(BaseModel):
    """Everything on the bus uses this shape (also what the console shows)."""

    run_id: str
    tick: int
    sender: str  # agent id, "router", "runbook", "validator", "human", ...
    type: MessageType
    content: dict[str, Any] = Field(default_factory=dict)
    rationale: str = ""  # short plain-English reason, shown in the ledger


class RunMetrics(BaseModel):
    """Results of one scenario run (used for evaluation)."""

    scenario: ScenarioId
    mode: Mode
    seed: int
    true_fault: Hypothesis
    recovery_time: int  # ticks until recovered (capped at 30)
    availability: float
    unnecessary_actions: int
    correct_diagnosis: bool
    escalated_to_human: bool = False
    brier_score: float | None = None
    llm_calls: int = 0


# --------------------------------------------------------------------------
# Interfaces (what each side promises the other)
# --------------------------------------------------------------------------
class SimulatorAPI(Protocol):
    """Person A builds this."""

    def reset(self, scenario: ScenarioId, seed: int) -> None: ...

    def step(self, action: Action) -> dict[str, float]:
        """Apply an action, advance one tick, return the full raw state."""
        ...

    def observe(self, agent_id: str) -> Observation:
        """Return ONLY this agent's visible data."""
        ...

    def is_recovered(self) -> bool: ...


class BeliefEngineAPI(Protocol):
    """Person A builds this."""

    def update(self, agent_id: str, belief: Belief, levels: dict[str, Level]) -> Belief: ...


class BusAPI(Protocol):
    """Person B builds this."""

    def publish(self, message: Message) -> None: ...

    def subscribe(self, handler: Callable[[Message], None]) -> None: ...
