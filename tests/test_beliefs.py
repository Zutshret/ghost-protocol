"""Tests for the likelihood estimation (A4) and the belief engine (A5)."""

import math
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from intelligence.beliefs import (  # noqa: E402
    BeliefEngine,
    brier,
    entropy,
    failed_action_update,
    load_table,
    log_pool,
)
from intelligence.estimate import collect_counts, to_probabilities  # noqa: E402
from shared.types import Action, Hypothesis, Level, uniform_belief  # noqa: E402

H = Hypothesis
L = Level


@pytest.fixture(scope="module")
def engine():
    return BeliefEngine()


def test_table_rows_are_probabilities():
    table = load_table()
    assert set(table) == {h.value for h in H}
    for features in table.values():
        for cell in features.values():
            assert sum(cell.values()) == pytest.approx(1.0)
            assert all(p > 0 for p in cell.values())  # smoothing: never exactly 0


def test_table_matches_a_fresh_estimate_on_a_small_sample():
    """The saved table should agree with re-counting from the simulator (same seeds -> same numbers)."""
    fresh = to_probabilities(collect_counts(seeds=range(1000, 1010)))
    saved = load_table()
    # Only the strongest signature is compared (small sample, so loose tolerance).
    assert fresh["db_fault"]["replication_lag_s"]["high"] > 0.8
    assert saved["db_fault"]["replication_lag_s"]["high"] > 0.8
    assert fresh["bad_deploy"]["minutes_since_deploy"]["low"] > 0.8


def test_beliefs_always_sum_to_one(engine):
    b = engine.update("x", uniform_belief(), {"replication_lag_s": L.HIGH, "traffic_anomaly": L.LOW})
    assert sum(b.values()) == pytest.approx(1.0)


def test_no_clues_means_no_change(engine):
    assert engine.update("x", uniform_belief(), {}) == pytest.approx(uniform_belief())


def test_unknown_features_are_ignored(engine):
    b = engine.update("network_analyst", uniform_belief(), {"downstream_p99_ms": L.HIGH})
    assert b == pytest.approx(uniform_belief())


@pytest.mark.parametrize(
    "levels, expected",
    [
        ({"replication_lag_s": L.HIGH, "slow_queries": L.HIGH, "lock_waits": L.HIGH}, H.DB_FAULT),
        ({"traffic_anomaly": L.HIGH, "failed_logins": L.HIGH, "suspicious_sources": L.HIGH}, H.ATTACK),
        ({"minutes_since_deploy": L.LOW, "canary_error_rate": L.HIGH}, H.BAD_DEPLOY),
        ({"upstream_timeouts": L.HIGH, "latency_ms": L.HIGH}, H.DEPENDENCY_TIMEOUT),
    ],
)
def test_each_signature_points_to_its_cause(engine, levels, expected):
    b = engine.update("x", uniform_belief(), levels)
    assert max(b, key=b.get) == expected
    # Two clues alone can legitimately be ambiguous (attack also raises timeouts,
    # a db fault also raises latency), so only require a clear plurality.
    assert b[expected] > 0.5


def test_the_s2_story_deployment_evidence_overturns_the_attack_guess(engine):
    """Security alone says attack; adding the Deployment agent's clues flips it to bad_deploy."""
    security = engine.update("security", uniform_belief(), {"traffic_anomaly": L.HIGH, "failed_logins": L.HIGH})
    assert max(security, key=security.get) == H.ATTACK
    both = engine.update("deployment", security, {"minutes_since_deploy": L.LOW, "canary_error_rate": L.HIGH})
    assert max(both, key=both.get) == H.BAD_DEPLOY


def test_order_of_clues_does_not_matter(engine):
    a = {"replication_lag_s": L.HIGH}
    b = {"traffic_anomaly": L.MEDIUM}
    one = engine.update("x", engine.update("x", uniform_belief(), a), b)
    two = engine.update("x", engine.update("x", uniform_belief(), b), a)
    assert one == pytest.approx(two)


def test_temperature_softens_confidence():
    levels = {"replication_lag_s": L.HIGH, "slow_queries": L.HIGH}
    sharp = BeliefEngine(temperature=1.0).update("x", uniform_belief(), levels)[H.DB_FAULT]
    soft = BeliefEngine(temperature=0.25).update("x", uniform_belief(), levels)[H.DB_FAULT]
    assert soft < sharp


def test_explain_ranks_decisive_clues_first(engine):
    rows = engine.explain({"replication_lag_s": L.HIGH, "config_changes": L.LOW})
    assert rows[0]["feature"] == "replication_lag_s"
    assert rows[0]["support_bits"]["db_fault"] > 0


# ---------------- helpers ----------------
def test_failed_action_lowers_what_it_fixes():
    b = failed_action_update(uniform_belief(), Action.BLOCK_TRAFFIC)
    assert b[H.ATTACK] < 0.25 < b[H.DB_FAULT]
    assert sum(b.values()) == pytest.approx(1.0)


def test_log_pool_of_agreeing_beliefs_is_sharper_and_disagreement_is_balanced():
    a = {H.DB_FAULT: 0.7, H.ATTACK: 0.1, H.BAD_DEPLOY: 0.1, H.DEPENDENCY_TIMEOUT: 0.1}
    assert log_pool([a, a])[H.DB_FAULT] > 0.7
    x = {H.DB_FAULT: 0.9, H.ATTACK: 0.1 / 3, H.BAD_DEPLOY: 0.1 / 3, H.DEPENDENCY_TIMEOUT: 0.1 / 3}
    y = {H.ATTACK: 0.9, H.DB_FAULT: 0.1 / 3, H.BAD_DEPLOY: 0.1 / 3, H.DEPENDENCY_TIMEOUT: 0.1 / 3}
    pooled = log_pool([x, y])
    assert pooled[H.DB_FAULT] == pytest.approx(pooled[H.ATTACK])  # a standoff stays a standoff


def test_entropy_and_brier():
    assert entropy(uniform_belief()) == pytest.approx(2.0)
    certain = {h: (1.0 if h == H.ATTACK else 0.0) for h in H}
    assert entropy(certain) == pytest.approx(0.0)
    assert brier(certain, H.ATTACK) == pytest.approx(0.0)
    assert brier(certain, H.DB_FAULT) == pytest.approx(2.0)
    assert not math.isnan(brier(uniform_belief(), H.ATTACK))
