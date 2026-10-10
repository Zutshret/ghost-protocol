import pytest

from shared.types import (
    AGENT_FEATURES,
    CORRECT_FIX,
    Action,
    Hypothesis,
    Level,
    ScenarioId,
)
from simulator.faults import level_of
from simulator.sim import Simulator

FAULT_START = Simulator.FAULT_START


def run(sim: Simulator, ticks: int, action_at: dict[int, Action] | None = None, **kwargs):
    """Advance `ticks` ticks, applying actions at specific ticks."""
    action_at = action_at or {}
    for _ in range(ticks):
        sim.step(action_at.get(sim.tick, Action.NOOP), **kwargs)


# ---------------- repeatability ----------------
def test_same_seed_same_run():
    a, b = Simulator(), Simulator()
    a.reset(ScenarioId.S2, 7)
    b.reset(ScenarioId.S2, 7)
    for _ in range(15):
        a.step(Action.NOOP)
        b.step(Action.NOOP)
        assert a.readings == b.readings


def test_different_seed_different_readings():
    a, b = Simulator(), Simulator()
    a.reset(ScenarioId.S1, 1)
    b.reset(ScenarioId.S1, 2)
    run(a, 10)
    run(b, 10)
    assert a.readings != b.readings


def test_observe_does_not_change_the_run():
    a, b = Simulator(), Simulator()
    a.reset(ScenarioId.S1, 3)
    b.reset(ScenarioId.S1, 3)
    for _ in range(10):
        for agent in AGENT_FEATURES:
            a.observe(agent)  # a looks a lot, b never looks
        a.step()
        b.step()
    assert a.readings == b.readings


def test_probe_choice_does_not_shift_later_randomness():
    # Probing changes what one tick looks like, but later ticks stay comparable.
    a, b = Simulator(), Simulator()
    a.reset(ScenarioId.S1, 5)
    b.reset(ScenarioId.S1, 5)
    a.step(Action.NOOP)
    b.step(Action.PROBE, probe_feature="lock_waits")
    a.step(Action.NOOP)
    b.step(Action.NOOP)
    assert a.readings == b.readings


# ---------------- partial observability ----------------
def test_each_agent_sees_only_its_own_features():
    sim = Simulator()
    sim.reset(ScenarioId.S1, 0)
    run(sim, 8)
    for agent, features in AGENT_FEATURES.items():
        obs = sim.observe(agent)
        assert set(obs.values) == set(features)
        assert set(obs.levels) == set(features)
        assert len(obs.logs) == len(features)


# ---------------- fault signatures (noise-free truth) ----------------
@pytest.mark.parametrize(
    "fault, high_feature",
    [
        (Hypothesis.DB_FAULT, "replication_lag_s"),
        (Hypothesis.BAD_DEPLOY, "canary_error_rate"),
        (Hypothesis.ATTACK, "traffic_anomaly"),
        (Hypothesis.DEPENDENCY_TIMEOUT, "upstream_timeouts"),
    ],
)
def test_fault_gets_worse_with_no_action(fault, high_feature):
    sim = Simulator()
    sim.reset(fault, 0)
    run(sim, FAULT_START + 6)
    assert sim.severity == 1.0
    assert level_of(high_feature, sim.clean[high_feature]) == Level.HIGH
    assert not sim.is_recovered()
    assert sim.edge_error_true > 0.05


def test_healthy_before_fault_starts():
    sim = Simulator()
    sim.reset(Hypothesis.DB_FAULT, 0)
    run(sim, FAULT_START - 1)  # tick = 4
    assert sim.severity == 0.0
    assert not sim.is_recovered()  # "recovered" only counts after the fault begins
    assert level_of("replication_lag_s", sim.clean["replication_lag_s"]) == Level.LOW


def test_db_fault_signature_is_distinct():
    sim = Simulator()
    sim.reset(Hypothesis.DB_FAULT, 0)
    run(sim, 12)
    assert level_of("traffic_anomaly", sim.clean["traffic_anomaly"]) == Level.LOW
    # a deploy long ago is a BIG number, so level HIGH (normal)
    assert level_of("minutes_since_deploy", sim.clean["minutes_since_deploy"]) == Level.HIGH


def test_bad_deploy_signature():
    sim = Simulator()
    sim.reset(Hypothesis.BAD_DEPLOY, 0)
    run(sim, 12)
    # a RECENT deploy is a small number, so level LOW
    assert level_of("minutes_since_deploy", sim.clean["minutes_since_deploy"]) == Level.LOW
    assert level_of("replication_lag_s", sim.clean["replication_lag_s"]) == Level.LOW


def test_noisy_readings_usually_show_the_signature():
    """With noise and flaky readings, most seeds should still read 'high'."""
    hits = 0
    for seed in range(100):
        sim = Simulator()
        sim.reset(ScenarioId.S1, seed)
        run(sim, 12)
        if sim.observe("database").levels["replication_lag_s"] == Level.HIGH:
            hits += 1
    assert 80 <= hits <= 100


# ---------------- fixing things ----------------
@pytest.mark.parametrize("fault", list(Hypothesis))
def test_correct_fix_recovers(fault):
    sim = Simulator()
    sim.reset(fault, 1)
    fix = CORRECT_FIX[fault]
    run(sim, 20, action_at={FAULT_START + 2: fix})
    assert sim.is_recovered()
    assert sim.recovery_time <= 10
    summary = sim.summary()
    assert summary["correct_diagnosis"] is True
    assert summary["unnecessary_actions"] == 0


@pytest.mark.parametrize("fault", list(Hypothesis))
def test_wrong_action_does_not_recover_and_is_counted(fault):
    wrong = next(
        a
        for a in (
            Action.ROLLBACK_DEPLOY,
            Action.BLOCK_TRAFFIC,
            Action.FAILOVER_DB,
            Action.RESTART_SERVICE,
        )
        if a != CORRECT_FIX[fault]
    )
    sim = Simulator()
    sim.reset(fault, 1)
    run(sim, 20, action_at={FAULT_START + 2: wrong})
    assert not sim.is_recovered()
    assert sim.recovery_time == Simulator.N_TICKS
    summary = sim.summary()
    assert summary["unnecessary_actions"] == 1
    assert summary["correct_diagnosis"] is False


def test_correct_fix_before_fault_has_no_effect():
    sim = Simulator()
    sim.reset(Hypothesis.BAD_DEPLOY, 0)
    run(sim, 20, action_at={2: Action.ROLLBACK_DEPLOY})
    assert not sim.is_recovered()
    assert sim.summary()["unnecessary_actions"] == 1


def test_repeating_the_correct_fix_counts_as_unnecessary():
    sim = Simulator()
    sim.reset(Hypothesis.DB_FAULT, 0)
    run(sim, 8, action_at={FAULT_START: Action.FAILOVER_DB, FAULT_START + 1: Action.FAILOVER_DB})
    assert sim.summary()["unnecessary_actions"] == 1


def test_probe_and_noop_are_not_unnecessary_actions():
    sim = Simulator()
    sim.reset(Hypothesis.DB_FAULT, 0)
    run(sim, 4, action_at={5: Action.PROBE, 6: Action.NOOP})
    sim.step(Action.PROBE)
    sim.step(Action.NOOP)
    assert sim.summary()["unnecessary_actions"] == 0


# ---------------- side effects ----------------
def test_blocking_traffic_without_attack_hurts_availability():
    wrong, right = Simulator(), Simulator()
    wrong.reset(ScenarioId.S2, 1)
    right.reset(ScenarioId.S2, 1)
    run(wrong, 25, action_at={FAULT_START + 2: Action.BLOCK_TRAFFIC, FAULT_START + 8: Action.ROLLBACK_DEPLOY})
    run(right, 25, action_at={FAULT_START + 2: Action.ROLLBACK_DEPLOY})
    assert wrong.availability() < right.availability()
    assert wrong.summary()["unnecessary_actions"] == 1
    assert wrong.recovery_time > right.recovery_time


def test_failover_is_safe_in_s1_but_risky_in_s5():
    s1, s5, s5_ok = Simulator(), Simulator(), Simulator()
    s1.reset(ScenarioId.S1, 1)
    s5.reset(ScenarioId.S5, 1)
    s5_ok.reset(ScenarioId.S5, 1)
    run(s1, 15, action_at={10: Action.FAILOVER_DB})
    run(s5, 15, action_at={10: Action.FAILOVER_DB})
    run(s5_ok, 15, action_at={10: Action.FAILOVER_DB}, approved=True)
    assert s1.consistency_violations == 0
    assert s5.consistency_violations == 1
    assert s5_ok.consistency_violations == 0  # a human accepted the risk
    assert s5.is_recovered()  # the risky fix still works


def test_probe_gives_clean_reading():
    sim = Simulator()
    sim.reset(ScenarioId.S1, 4)
    run(sim, 9)
    sim.step(Action.PROBE, probe_feature="replication_lag_s")
    assert sim.readings["replication_lag_s"] == pytest.approx(sim.clean["replication_lag_s"], abs=1e-3)
    assert sim.last_probe == {"replication_lag_s": sim.readings["replication_lag_s"]}
    assert "verified" in " ".join(sim.observe("database").logs)
    sim.step(Action.NOOP)
    assert sim.last_probe == {}


# ---------------- scenarios ----------------
def test_s2_decoy_shows_up_on_about_40_percent_of_seeds():
    decoy_runs = 0
    for seed in range(300):
        sim = Simulator()
        sim.reset(ScenarioId.S2, seed)
        if sim.active_decoys:
            decoy_runs += 1
    assert 0.30 <= decoy_runs / 300 <= 0.50


def test_s2_decoy_fools_security_signals_but_truth_is_deploy():
    for seed in range(50):
        sim = Simulator()
        sim.reset(ScenarioId.S2, seed)
        if sim.active_decoys:
            run(sim, 12)
            assert level_of("traffic_anomaly", sim.clean["traffic_anomaly"]) == Level.HIGH
            assert sim.true_fault == Hypothesis.BAD_DEPLOY
            assert level_of("minutes_since_deploy", sim.clean["minutes_since_deploy"]) == Level.LOW
            return
    pytest.fail("no decoy seed found")


def test_s5_signals_are_mixed():
    sim = Simulator()
    sim.reset(ScenarioId.S5, 0)
    run(sim, 12)
    assert level_of("replication_lag_s", sim.clean["replication_lag_s"]) == Level.HIGH
    assert level_of("traffic_anomaly", sim.clean["traffic_anomaly"]) in (Level.MEDIUM, Level.HIGH)
    assert level_of("minutes_since_deploy", sim.clean["minutes_since_deploy"]) == Level.HIGH  # no recent deploy


# ---------------- Person B's backend expectations ----------------
def test_state_has_the_keys_person_b_reads():
    sim = Simulator()
    sim.reset(ScenarioId.S1, 0)
    full = sim.step(Action.NOOP)
    for key in ("error_rate", "latency_ms", "customer_lockout"):
        assert key in full
    assert sim.state.keys() == sim.truth.keys()
    assert sim.tick == 1


def test_s3_is_a_dependency_timeout():
    sim = Simulator()
    sim.reset(ScenarioId.S3, 0)
    assert sim.true_fault == Hypothesis.DEPENDENCY_TIMEOUT
    run(sim, 12)
    assert level_of("upstream_timeouts", sim.clean["upstream_timeouts"]) == Level.HIGH


def test_unknown_agent_raises_keyerror():
    """Person B's backend relies on this to fall back for the recruited Network Analyst."""
    sim = Simulator()
    sim.reset(ScenarioId.S1, 0)
    with pytest.raises(KeyError):
        sim.observe("network_analyst")


def test_recent_deploy_log_line_is_loud():
    sim = Simulator()
    sim.reset(Hypothesis.BAD_DEPLOY, 0)
    run(sim, 10)
    line = sim.observe("deployment").logs[0]
    assert line.startswith("ERROR") and "last deploy" in line


# ---------------- run limits ----------------
def test_step_after_30_ticks_raises():
    sim = Simulator()
    sim.reset(ScenarioId.S1, 0)
    run(sim, Simulator.N_TICKS)
    assert sim.finished
    with pytest.raises(RuntimeError):
        sim.step()


def test_availability_is_between_zero_and_one():
    sim = Simulator()
    sim.reset(ScenarioId.S1, 0)
    run(sim, Simulator.N_TICKS)
    assert 0.0 <= sim.availability() <= 1.0
