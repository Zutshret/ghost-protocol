"""The deterministic runbook (Mode A baseline, task A3).

A fixed list of if-then rules, like a real operations runbook. It is
deliberately realistic, not stupid:
- it wins on clear failures (S1), fast and cheap;
- it misfires when the evidence is misleading (S2 decoy: "error spike + odd
  traffic" looks like an attack, but it was really a bad deploy).

How it behaves:
1. Watch overall health. Open an incident after 3 bad ticks in a row (so one
   flaky reading does not trigger anything).
2. Try the first matching rule that the safety validator allows.
3. Wait a few ticks. If things did not clearly improve, mark that rule as
   failed and try the next matching rule.
4. If nothing matches or everything is blocked, do nothing (a person is needed).

`runbook_matches(levels)` has the same name and signature as the stand-in used
by Person B's backend.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.types import Action, Level
from simulator.validator import validate


@dataclass(frozen=True)
class Rule:
    name: str
    action: Action
    when: str  # plain-English condition (shown in the console ledger)


# Order matters: the first matching rule wins.
RULES: list[Rule] = [
    Rule("db_lag", Action.FAILOVER_DB, "replication_lag_s high AND slow_queries high"),
    Rule("traffic_spike", Action.BLOCK_TRAFFIC, "error spike AND traffic_anomaly high"),
    Rule("recent_deploy", Action.ROLLBACK_DEPLOY, "deploy < 30 min ago AND error spike"),
    Rule("upstream_timeouts", Action.RESTART_SERVICE, "upstream_timeouts high AND latency high"),
]


def runbook_matches(levels: dict[str, Level]) -> list[Rule]:
    """Which rules match the current levels (in rule order)?"""

    def high(feature: str) -> bool:
        return levels.get(feature) == Level.HIGH

    spike = high("edge_error_rate") or high("payment_error_rate")
    checks = {
        "db_lag": high("replication_lag_s") and high("slow_queries"),
        "traffic_spike": spike and high("traffic_anomaly"),
        "recent_deploy": levels.get("minutes_since_deploy") == Level.LOW and spike,
        "upstream_timeouts": high("upstream_timeouts") and high("latency_ms"),
    }
    return [rule for rule in RULES if checks[rule.name]]


def badness(readings: dict[str, float]) -> float:
    """1.0 or more means 'unhealthy' (error rate >= 2% or latency >= 300 ms)."""
    return max(readings.get("edge_error_rate", 0.0) / 0.02, readings.get("latency_ms", 0.0) / 300.0)


@dataclass
class Runbook:
    BAD_TICKS_TO_OPEN: int = 3  # bad ticks in a row before an incident opens
    HOLD_TICKS: int = 4  # wait this long after an action before judging it
    IMPROVE_FACTOR: float = 0.5  # "worked" = badness fell below this share of its peak

    bad_streak: int = 0
    incident_open: bool = False
    failed_rules: set[str] = field(default_factory=set)
    pending: tuple[Rule, int, float] | None = None  # (rule, tick fired, badness then)
    working: bool = False  # the last action is clearly helping; just wait
    badness_history: list[float] = field(default_factory=list)
    # Explanation of the latest decision (for the ledger / debugging).
    last_note: str = ""
    last_rule: Rule | None = None
    blocked_log: list[str] = field(default_factory=list)

    def reset(self) -> None:
        self.bad_streak = 0
        self.incident_open = False
        self.failed_rules = set()
        self.pending = None
        self.working = False
        self.badness_history = []
        self.last_note = ""
        self.last_rule = None
        self.blocked_log = []

    def decide(self, tick: int, readings: dict[str, float], levels: dict[str, Level]) -> Action:
        """Pick this tick's action from ALL telemetry (the runbook sees every dashboard)."""
        self.last_rule = None
        b = badness(readings)
        self.badness_history.append(b)
        self.bad_streak = self.bad_streak + 1 if b >= 1.0 else 0

        if not self.incident_open:
            if self.bad_streak >= self.BAD_TICKS_TO_OPEN:
                self.incident_open = True
                self.last_note = f"incident opened after {self.bad_streak} bad ticks"
            else:
                self.last_note = "healthy" if b < 1.0 else f"watching ({self.bad_streak} bad tick(s))"
                return Action.NOOP

        if self.working:
            self.last_note = "last action is helping; waiting for recovery"
            return Action.NOOP

        if self.pending is not None:
            rule, fired_at, b0 = self.pending
            if tick - fired_at < self.HOLD_TICKS:
                self.last_note = f"waiting to see whether '{rule.name}' ({rule.action.value}) helps"
                return Action.NOOP
            recent = sum(self.badness_history[-2:]) / len(self.badness_history[-2:])
            if recent < self.IMPROVE_FACTOR * b0:
                self.working = True
                self.pending = None
                self.last_note = f"'{rule.name}' worked; waiting for recovery"
                return Action.NOOP
            self.failed_rules.add(rule.name)
            self.pending = None
            self.last_note = f"'{rule.name}' did not help; trying the next rule"

        for rule in runbook_matches(levels):
            if rule.name in self.failed_rules:
                continue
            verdict = validate(rule.action, readings)
            if not verdict.allowed:
                msg = f"tick {tick}: rule '{rule.name}' blocked by validator ({verdict.reason})"
                self.blocked_log.append(msg)
                self.last_note = msg
                continue
            peak = max(self.badness_history[-3:])
            self.pending = (rule, tick, peak)
            self.last_rule = rule
            self.last_note = f"rule '{rule.name}' matched ({rule.when}) -> {rule.action.value}"
            return rule.action

        if not self.last_note.startswith("tick"):
            self.last_note = "no safe rule matches; a person is needed"
        return Action.NOOP
