"""STAND-IN simulator, used only until Person A's simulator/sim.py lands.

Follows the "Simulator cheat sheet" in the plan so agents, backend and console
can be built and demoed now. backend/adapters.py prefers the real one.
"""

from __future__ import annotations

import random

from shared.types import (
    AGENT_FEATURES,
    CORRECT_FIX,
    FEATURE_BASELINES,
    Action,
    Hypothesis,
    Level,
    Observation,
    ScenarioId,
)

RUN_TICKS = 30
FAULT_TICK = 5
NOISE = 0.10
FLAKY_P = 0.05
FIX_TICKS = 4

# Extra features only the recruited Network Analyst can see.
EXTRA_BASELINES = {"downstream_p99_ms": 150.0, "conn_pool_saturation": 0.3}
EXTRA_FEATURES = {"network_analyst": ["downstream_p99_ms", "conn_pool_saturation", "upstream_timeouts"]}
ALL_BASELINES = {**FEATURE_BASELINES, **EXTRA_BASELINES}

# value < medium -> low; value < high -> medium; else high
THRESHOLDS: dict[str, tuple[float, float]] = {
    "request_rate": (140, 200),
    "edge_error_rate": (0.03, 0.08),
    "upstream_timeouts": (6, 15),
    "payment_error_rate": (0.03, 0.08),
    "queue_depth": (25, 60),
    "latency_ms": (200, 400),
    "replication_lag_s": (1.5, 5),
    "slow_queries": (8, 20),
    "lock_waits": (6, 15),
    "traffic_anomaly": (0.35, 0.65),
    "failed_logins": (15, 40),
    "suspicious_sources": (4, 10),
    "minutes_since_deploy": (15, 120),
    "canary_error_rate": (0.03, 0.08),
    "config_changes": (1, 3),
    "downstream_p99_ms": (400, 1000),
    "conn_pool_saturation": (0.6, 0.85),
}


def to_level(feature: str, value: float) -> Level:
    med, high = THRESHOLDS[feature]
    if value < med:
        return Level.LOW
    if value < high:
        return Level.MEDIUM
    return Level.HIGH


# Fully developed fault values (severity 1). Unlisted features stay at baseline.
FAULT_TARGETS: dict[Hypothesis, dict[str, float]] = {
    Hypothesis.DB_FAULT: {
        "replication_lag_s": 9, "slow_queries": 35, "lock_waits": 25,
        "payment_error_rate": 0.10, "queue_depth": 70, "latency_ms": 520,
    },
    Hypothesis.BAD_DEPLOY: {
        "canary_error_rate": 0.15, "payment_error_rate": 0.12,
        "edge_error_rate": 0.10, "config_changes": 2,
    },
    Hypothesis.ATTACK: {
        "traffic_anomaly": 0.85, "failed_logins": 80, "suspicious_sources": 18,
        "request_rate": 320, "upstream_timeouts": 12, "edge_error_rate": 0.11,
    },
    Hypothesis.DEPENDENCY_TIMEOUT: {
        "upstream_timeouts": 30, "latency_ms": 650, "queue_depth": 80,
        "payment_error_rate": 0.05, "edge_error_rate": 0.05,
        "downstream_p99_ms": 2200, "conn_pool_saturation": 0.95,
    },
}

S2_DECOY = {"traffic_anomaly": 0.75, "failed_logins": 55}
# S5: a medium db fault plus a coincident, attack-like traffic surge.
S5_TARGETS = {
    "replication_lag_s": 7.5, "slow_queries": 16, "lock_waits": 11,
    "payment_error_rate": 0.06, "edge_error_rate": 0.10, "queue_depth": 45,
    "latency_ms": 330, "traffic_anomaly": 0.72, "failed_logins": 32,
    "suspicious_sources": 8, "request_rate": 185, "upstream_timeouts": 10,
}

SCENARIO_FAULT = {
    ScenarioId.S1: Hypothesis.DB_FAULT,
    ScenarioId.S2: Hypothesis.BAD_DEPLOY,
    ScenarioId.S3: Hypothesis.DEPENDENCY_TIMEOUT,
    ScenarioId.S5: Hypothesis.DB_FAULT,
}


class StandInSimulator:
    def __init__(self) -> None:
        self.reset(ScenarioId.S1, 0)

    def reset(self, scenario: ScenarioId, seed: int) -> None:
        self.scenario = ScenarioId(scenario)
        self.seed = seed
        self.rng = random.Random(seed)
        self.true_fault = SCENARIO_FAULT[self.scenario]
        self.decoy = self.scenario == ScenarioId.S2 and self.rng.random() < 0.4
        self.tick = 0
        self.fixed_at: int | None = None
        self.lockout_until = -1
        self.probe_next = False
        self.deploy_tick = 3 if self.true_fault == Hypothesis.BAD_DEPLOY else -600
        self.actions: list[tuple[int, Action]] = []
        self.healthy_streak = 0
        self.state = self._sample()

    # --- dynamics -----------------------------------------------------------
    def _severity(self) -> float:
        if self.tick < FAULT_TICK:
            return 0.0
        onset = min(1.0, (self.tick - FAULT_TICK + 1) / 2)
        if self.fixed_at is None:
            return onset
        return onset * max(0.0, 1 - (self.tick - self.fixed_at) / FIX_TICKS)

    def _targets(self) -> dict[str, float]:
        if self.scenario == ScenarioId.S5:
            t = dict(S5_TARGETS)
        else:
            t = dict(FAULT_TARGETS[self.true_fault])
            if self.decoy:
                t.update(S2_DECOY)
        return t

    def _sample(self) -> dict[str, float]:
        sev = self._severity()
        targets = self._targets()
        noise = NOISE / 3 if self.probe_next else NOISE
        out: dict[str, float] = {}
        for f, base in ALL_BASELINES.items():
            v = base + sev * (targets.get(f, base) - base)
            if f == "minutes_since_deploy":
                v = float(self.tick - self.deploy_tick)
            v *= 1 + self.rng.gauss(0, noise)
            if not self.probe_next and self.rng.random() < FLAKY_P:
                v = self.rng.uniform(0, 2.5 * THRESHOLDS[f][1])
            out[f] = max(0.0, v)
        lockout = 0.15 if self.tick <= self.lockout_until else 0.0
        out["customer_lockout"] = lockout
        out["error_rate"] = max(out["edge_error_rate"], out["payment_error_rate"])
        self.probe_next = False
        return out

    def step(self, action: Action) -> dict[str, float]:
        action = Action(action)
        if action not in (Action.NOOP, Action.PROBE):
            self.actions.append((self.tick, action))
        if action == CORRECT_FIX[self.true_fault] and self.tick >= FAULT_TICK and self.fixed_at is None:
            self.fixed_at = self.tick
        if action == Action.ROLLBACK_DEPLOY:
            self.deploy_tick = self.tick  # a rollback is itself a deploy
        if action == Action.BLOCK_TRAFFIC and self.true_fault != Hypothesis.ATTACK:
            self.lockout_until = self.tick + 6
        if action == Action.PROBE:
            self.probe_next = True
        self.tick += 1
        self.state = self._sample()
        healthy = self.state["error_rate"] < 0.02 and self.state["latency_ms"] < 300
        self.healthy_streak = self.healthy_streak + 1 if healthy else 0
        return dict(self.state)

    def is_recovered(self) -> bool:
        return self.tick > FAULT_TICK and self.healthy_streak >= 3

    def observe(self, agent_id: str) -> Observation:
        features = AGENT_FEATURES.get(agent_id) or EXTRA_FEATURES[agent_id]
        values = {f: round(self.state[f], 4) for f in features}
        levels = {f: to_level(f, v) for f, v in values.items()}
        return Observation(
            agent_id=agent_id, tick=self.tick, values=values, levels=levels,
            logs=_log_lines(agent_id, self.tick, values),
        )


def _log_lines(agent_id: str, tick: int, values: dict[str, float]) -> list[str]:
    lines = []
    for f, v in values.items():
        base = ALL_BASELINES[f]
        ratio = v / base if base else (v + 1)
        sev = "ERROR" if ratio > 4 or (f == "minutes_since_deploy" and v < 15) else "WARN" if ratio > 1.8 else "INFO"
        lines.append(f"t={tick} [{agent_id}] {sev} {f}={v:g} (baseline {base:g})")
    return lines
