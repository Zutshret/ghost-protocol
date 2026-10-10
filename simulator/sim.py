"""The GHOST PROTOCOL simulator (task A1).

A pretend payments platform that breaks in one of four ways. It produces noisy
readings (what agents see) while keeping a hidden, noise-free "ground truth"
(what we use to score them).

Key ideas:
- One run is 30 ticks (think: minutes). The fault starts at tick 5.
- The fault ramps up over a few ticks ("severity" goes 0 -> 1).
- The correct fix ramps severity back down to 0; wrong actions change nothing.
- All randomness comes from the seed, so the same seed and the same actions
  always give exactly the same run.

Agents must only use `observe()`. The dictionary returned by `step()` and the
`truth` property contain ground truth and are for scoring/debugging only.
"""

from __future__ import annotations

from typing import Any

import numpy as np

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
from simulator.faults import (
    COUNT_FEATURES,
    FAULT_PEAKS,
    FEATURE_MAX,
    RATE_FEATURES,
    SMALL_IS_ABNORMAL,
    level_of,
)
from simulator.scenarios import SCENARIOS, ScenarioSpec, custom_scenario

# Actions that actually change the system (probe/noop do not).
STATE_CHANGING = {
    Action.ROLLBACK_DEPLOY,
    Action.BLOCK_TRAFFIC,
    Action.FAILOVER_DB,
    Action.RESTART_SERVICE,
}

_LOG_PREFIX = {Level.LOW: "INFO", Level.MEDIUM: "WARN", Level.HIGH: "ERROR"}
_LOG_TEMPLATE = {
    "request_rate": "gateway request rate {:.0f}/s",
    "edge_error_rate": "gateway edge 5xx rate {:.1%}",
    "upstream_timeouts": "gateway upstream timeouts {:.0f} in last tick",
    "payment_error_rate": "payments call failure rate {:.1%}",
    "queue_depth": "payments queue depth {:.0f}",
    "latency_ms": "payments p95 latency {:.0f} ms",
    "replication_lag_s": "db replica lag {:.1f} s",
    "slow_queries": "db slow queries {:.0f}",
    "lock_waits": "db lock waits {:.0f}",
    "traffic_anomaly": "traffic anomaly score {:.2f}",
    "failed_logins": "failed logins {:.0f} in last tick",
    "suspicious_sources": "suspicious source addresses {:.0f}",
    "minutes_since_deploy": "last deploy {:.0f} minutes ago",
    "canary_error_rate": "canary error rate {:.1%}",
    "config_changes": "config changes in last hour {:.0f}",
}


class Simulator:
    # --- Timing ---
    N_TICKS = 30  # length of a run
    FAULT_START = 5  # tick at which the fault begins
    RAMP_TICKS = 4  # ticks for the fault to reach full severity
    FIX_TICKS = 3  # ticks for the correct fix to bring severity to 0

    # --- Recovery definition ---
    HEALTHY_ERROR = 0.02  # edge error rate must be below this ...
    HEALTHY_LATENCY = 300.0  # ... and latency (ms) below this ...
    HEALTHY_STREAK = 3  # ... for this many ticks in a row

    # --- Noise ---
    NOISE_SIGMA = 0.10  # about 10% random noise on every reading
    FLAKY_PROB = 0.05  # chance a reading is replaced by a random value

    # --- Side effects ---
    CONSISTENCY_LAG_LIMIT = 12.0  # failover above this lag risks data consistency
    LOCKOUT_TICKS = 5  # how long a traffic block lasts
    LOCKOUT_WRONG = 0.20  # availability penalty if blocking when there is no attack
    LOCKOUT_RIGHT = 0.05  # small penalty even when blocking a real attack

    def __init__(self) -> None:
        self.reset(ScenarioId.S1, 0)

    # ------------------------------------------------------------------
    # Public API (matches SimulatorAPI in shared/types.py)
    # ------------------------------------------------------------------
    def reset(self, scenario: ScenarioId | ScenarioSpec | Hypothesis, seed: int = 0) -> None:
        """Start a new incident. Accepts S1/S2/S5, a ScenarioSpec, or a Hypothesis."""
        if isinstance(scenario, ScenarioSpec):
            self.spec = scenario
        elif isinstance(scenario, Hypothesis):
            self.spec = custom_scenario(scenario)
        else:
            self.spec = SCENARIOS[ScenarioId(scenario)]

        self.seed = seed
        self.rng = np.random.default_rng(seed)
        self.true_fault: Hypothesis = self.spec.true_fault

        # Decide once per run which decoys are present (always draw, for determinism).
        self.active_decoys = [d for d in self.spec.decoys if self.rng.random() < d.prob]

        self.tick = 0
        self.severity = 0.0
        self.fixed = False
        self.fixed_at: int | None = None
        self.block_ticks_left = 0
        self.lockout_penalty = 0.0
        self.healthy_streak = 0
        self.recovery_tick: int | None = None
        self.consistency_violations = 0
        self.actions_log: list[dict[str, Any]] = []
        self.availability_history: list[float] = []
        self.verified: set[str] = set()
        self.last_probe: dict[str, float] = {}

        self._refresh()

    def step(
        self,
        action: Action = Action.NOOP,
        *,
        approved: bool = False,
        probe_feature: str | None = None,
    ) -> dict[str, float]:
        """Apply an action at the current tick, advance one tick.

        approved:      a human accepted the risk (a failover above the lag limit
                       then does not count as a consistency violation).
        probe_feature: only used with Action.PROBE. The named feature (or ALL
                       features if None) is read cleanly on the next tick.

        Returns the full ground-truth state (NOT for agents).
        """
        if self.tick >= self.N_TICKS:
            raise RuntimeError("This run is over (30 ticks). Call reset() to start a new one.")

        action = Action(action)
        t = self.tick
        correct_action = CORRECT_FIX[self.true_fault]
        fault_active = t >= self.FAULT_START

        # --- effects of the action ---
        effective = False
        if action == correct_action and fault_active and not self.fixed:
            effective = True
            self.fixed = True
            self.fixed_at = t

        if action == Action.FAILOVER_DB:
            lag = self.clean["replication_lag_s"]
            if lag > self.CONSISTENCY_LAG_LIMIT and not approved:
                self.consistency_violations += 1

        if action == Action.BLOCK_TRAFFIC:
            self.block_ticks_left = self.LOCKOUT_TICKS

        needed = effective
        self.actions_log.append(
            {
                "tick": t,
                "action": action,
                "effective": effective,
                "unnecessary": action in STATE_CHANGING and not needed,
                "approved": approved,
            }
        )

        # --- probe: next tick's readings are clean ---
        if action == Action.PROBE:
            self.verified = {probe_feature} if probe_feature else set(FEATURE_BASELINES)
        else:
            self.verified = set()

        # --- advance one tick ---
        self.tick = t + 1
        if self.tick >= self.FAULT_START:
            if self.fixed:
                self.severity = max(0.0, self.severity - 1.0 / self.FIX_TICKS)
            else:
                self.severity = min(1.0, self.severity + 1.0 / self.RAMP_TICKS)

        if self.block_ticks_left > 0:
            self.lockout_penalty = (
                self.LOCKOUT_RIGHT if self.true_fault == Hypothesis.ATTACK else self.LOCKOUT_WRONG
            )
            self.block_ticks_left -= 1
        else:
            self.lockout_penalty = 0.0

        self._refresh()
        if action == Action.PROBE:
            self.last_probe = {f: self.readings[f] for f in self.verified}
        else:
            self.last_probe = {}
        return self.truth

    def observe(self, agent_id: str) -> Observation:
        """What ONE agent sees right now: only its own features (plus log lines)."""
        features = AGENT_FEATURES[agent_id]
        values = {f: self.readings[f] for f in features}
        levels = {f: level_of(f, v) for f, v in values.items()}
        logs = []
        for f in features:
            shown = levels[f]
            if f in SMALL_IS_ABNORMAL:  # a recent deploy (small number) deserves the loud label
                shown = {Level.LOW: Level.HIGH, Level.MEDIUM: Level.MEDIUM, Level.HIGH: Level.LOW}[shown]
            line = f"{_LOG_PREFIX[shown]} " + _LOG_TEMPLATE[f].format(values[f])
            if f in self.verified:
                line += " [verified by probe]"
            logs.append(line)
        return Observation(agent_id=agent_id, tick=self.tick, values=values, levels=levels, logs=logs)

    def is_recovered(self) -> bool:
        return self.recovery_tick is not None

    # ------------------------------------------------------------------
    # Helpers for runners, scoring, and debugging
    # ------------------------------------------------------------------
    @property
    def finished(self) -> bool:
        """True when the run is over (recovered, or all 30 ticks used)."""
        return self.is_recovered() or self.tick >= self.N_TICKS

    @property
    def recovery_time(self) -> int:
        """Ticks from fault start until recovery (capped at 30 if never recovered)."""
        if self.recovery_tick is None:
            return self.N_TICKS
        return self.recovery_tick - self.FAULT_START

    @property
    def truth(self) -> dict[str, float]:
        """Ground truth for scoring and debugging. Agents must NOT use this."""
        state = dict(self.clean)
        state.update(
            {
                "tick": float(self.tick),
                "severity": self.severity,
                "edge_error_rate_true": self.edge_error_true,
                "latency_ms_true": self.latency_true,
                "lockout_penalty": self.lockout_penalty,
                "availability": self.availability_history[-1],
                "healthy_streak": float(self.healthy_streak),
                # Names Person B's backend reads (overall health of the whole system):
                "error_rate": self.edge_error_true,
                "latency_ms": self.latency_true,  # replaces the per-feature value in this dict
                "customer_lockout": self.lockout_penalty,
            }
        )
        return state

    @property
    def state(self) -> dict[str, float]:
        """Same as `truth` (kept for Person B's backend, which looks for `sim.state`)."""
        return self.truth

    def availability(self) -> float:
        """Average availability over the full 30-tick window.

        If the run stopped early (recovered), the last value is assumed to continue.
        """
        hist = self.availability_history[: self.N_TICKS]
        if not hist:
            return 1.0
        hist = hist + [hist[-1]] * (self.N_TICKS - len(hist))
        return float(sum(hist) / len(hist))

    def summary(self) -> dict[str, Any]:
        """Scoring numbers for the finished (or in-progress) run."""
        changes = [a for a in self.actions_log if a["action"] in STATE_CHANGING]
        correct_action = CORRECT_FIX[self.true_fault]
        return {
            "true_fault": self.true_fault,
            "recovered": self.is_recovered(),
            "recovery_time": self.recovery_time,
            "availability": self.availability(),
            "unnecessary_actions": sum(1 for a in changes if a["unnecessary"]),
            "correct_diagnosis": bool(changes) and changes[0]["action"] == correct_action,
            "consistency_violations": self.consistency_violations,
            "ticks_run": self.tick,
        }

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------
    def _refresh(self) -> None:
        """Recompute clean values, readings, health, and availability for the current tick."""
        self.clean = self._compute_clean()
        self.readings = self._make_readings(self.verified)

        primary = FAULT_PEAKS[self.true_fault]
        self.edge_error_true = self._harm("edge_error_rate", primary)
        self.latency_true = self._harm("latency_ms", primary)

        availability = 1.0 - self.edge_error_true - self.lockout_penalty
        self.availability_history.append(float(min(1.0, max(0.0, availability))))

        # Recovery bookkeeping: healthy for N ticks in a row after the fault starts.
        if self.tick >= self.FAULT_START:
            healthy = (
                self.edge_error_true < self.HEALTHY_ERROR and self.latency_true < self.HEALTHY_LATENCY
            )
            self.healthy_streak = self.healthy_streak + 1 if healthy else 0
            if self.recovery_tick is None and self.healthy_streak >= self.HEALTHY_STREAK:
                self.recovery_tick = self.tick

    def _harm(self, feature: str, primary: dict[str, float]) -> float:
        """True harm level for a feature, driven only by the real fault (not decoys)."""
        base = FEATURE_BASELINES[feature]
        peak = self.spec.peak_overrides.get(feature, primary.get(feature, base))
        return base + self.severity * (peak - base)

    def _compute_clean(self) -> dict[str, float]:
        """Noise-free value of every feature at the current tick."""
        primary = FAULT_PEAKS[self.true_fault]
        clean: dict[str, float] = {}
        for feature, base in FEATURE_BASELINES.items():
            value = base
            peak = self.spec.peak_overrides.get(feature, primary.get(feature))
            if peak is not None:
                value = base + self.severity * (peak - base)
            for decoy in self.active_decoys:
                decoy_peaks = FAULT_PEAKS[decoy.hypothesis]
                if feature in decoy_peaks and (decoy.features is None or feature in decoy.features):
                    decoy_value = base + decoy.strength * self.severity * (decoy_peaks[feature] - base)
                    value = max(value, decoy_value)
            clean[feature] = value

        # Deploy-related features are step changes, not ramps.
        clean["minutes_since_deploy"] = 600.0 + self.tick
        if self.true_fault == Hypothesis.BAD_DEPLOY and self.tick >= self.FAULT_START:
            clean["minutes_since_deploy"] = float(self.tick - self.FAULT_START + 2)
            clean["config_changes"] = 2.0
        return clean

    def _make_readings(self, verified: set[str]) -> dict[str, float]:
        """Noisy readings. The random draws are fixed per tick so results are repeatable."""
        readings: dict[str, float] = {}
        for feature in FEATURE_BASELINES:
            z = self.rng.normal()  # always draw all three numbers, even if unused
            u = self.rng.random()
            w = self.rng.random()
            clean = self.clean[feature]
            if feature in verified:
                value = clean
            elif u < self.FLAKY_PROB:
                value = w * FEATURE_MAX[feature]
            else:
                value = clean * (1.0 + self.NOISE_SIGMA * z)
            readings[feature] = self._format(feature, value)
        return readings

    @staticmethod
    def _format(feature: str, value: float) -> float:
        value = max(0.0, value)
        if feature in RATE_FEATURES:
            value = min(1.0, value)
        if feature in COUNT_FEATURES:
            return float(round(value))
        return round(value, 3)
