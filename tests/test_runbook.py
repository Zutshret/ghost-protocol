"""Tests for the validator, the runbook, and the multi-seed runner (A2 + A3)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from eval.run_scenarios import run_mode_a, summarize  # noqa: E402
from shared.types import Action, Level, ScenarioId  # noqa: E402
from simulator.runbook import Runbook, runbook_matches  # noqa: E402
from simulator.validator import validate  # noqa: E402


# ---------------- validator ----------------
def test_failover_is_safe_when_lag_is_small():
    v = validate(Action.FAILOVER_DB, {"replication_lag_s": 2.0})
    assert v.allowed and not v.risky


def test_failover_is_risky_when_lag_is_medium():
    v = validate(Action.FAILOVER_DB, {"replication_lag_s": 8.0})
    assert v.allowed and v.risky


def test_failover_is_blocked_when_lag_is_huge_unless_human_approves():
    state = {"replication_lag_s": 15.0}
    assert not validate(Action.FAILOVER_DB, state).allowed
    approved = validate(Action.FAILOVER_DB, state, human_approved=True)
    assert approved.allowed and approved.risky


def test_block_traffic_is_always_risky_and_others_are_safe():
    assert validate(Action.BLOCK_TRAFFIC, {}).risky
    for a in (Action.NOOP, Action.ROLLBACK_DEPLOY, Action.RESTART_SERVICE):
        v = validate(a, {})
        assert v.allowed and not v.risky


# ---------------- runbook rules ----------------
def test_rules_match_the_obvious_cases():
    L = Level
    db = {"replication_lag_s": L.HIGH, "slow_queries": L.HIGH}
    assert [r.action for r in runbook_matches(db)] == [Action.FAILOVER_DB]
    deploy = {"minutes_since_deploy": L.LOW, "edge_error_rate": L.HIGH}
    assert [r.action for r in runbook_matches(deploy)] == [Action.ROLLBACK_DEPLOY]
    attack = {"traffic_anomaly": L.HIGH, "edge_error_rate": L.HIGH}
    assert [r.action for r in runbook_matches(attack)] == [Action.BLOCK_TRAFFIC]
    assert runbook_matches({"edge_error_rate": L.LOW}) == []


def test_runbook_stays_quiet_when_healthy():
    rb = Runbook()
    for t in range(10):
        assert rb.decide(t, {"edge_error_rate": 0.01, "latency_ms": 250}, {}) == Action.NOOP
    assert not rb.incident_open


def test_one_bad_tick_does_not_open_an_incident():
    rb = Runbook()
    rb.decide(0, {"edge_error_rate": 0.2, "latency_ms": 900}, {})
    rb.decide(1, {"edge_error_rate": 0.01, "latency_ms": 250}, {})
    assert not rb.incident_open and rb.bad_streak == 0


# ---------------- end-to-end baseline behaviour ----------------
def test_runbook_handles_the_clear_case_s1():
    for seed in range(10):
        row = run_mode_a(ScenarioId.S1, seed)
        assert row["recovered"] and row["correct_diagnosis"]
        assert row["unnecessary_actions"] == 0 and row["consistency_violations"] == 0


def test_runbook_is_fooled_by_the_s2_decoy_on_some_seeds():
    rows = [run_mode_a(ScenarioId.S2, seed) for seed in range(60)]
    fooled = [r for r in rows if not r["correct_diagnosis"]]
    assert 0 < len(fooled) < len(rows)  # sometimes fooled, not always
    assert all(r["recovered"] for r in rows)  # but it recovers eventually


def test_runbook_cannot_cleanly_resolve_s5():
    rows = [run_mode_a(ScenarioId.S5, seed) for seed in range(30)]
    clean = [r for r in rows if r["correct_diagnosis"] and r["recovered"]]
    assert len(clean) < len(rows) / 2
    assert any(r["blocked_by_validator"] > 0 for r in rows)  # the validator did its job


def test_runner_is_repeatable():
    assert run_mode_a(ScenarioId.S2, 7) == run_mode_a(ScenarioId.S2, 7)


def test_summary_has_the_expected_shape():
    rows = [run_mode_a(ScenarioId.S1, s) for s in range(5)]
    summary = summarize(rows)["S1"]
    assert summary["runs"] == 5 and summary["recovered_rate"] == 1.0
    assert set(summary["recovery_time"]) == {"mean", "ci95"}
