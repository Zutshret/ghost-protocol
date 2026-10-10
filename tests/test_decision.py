"""Tests for the act / probe / escalate decision rule (A6)."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from intelligence.decision import DEFAULT_COSTS, CostModel, decide, escalation_options  # noqa: E402
from shared.types import Action, Hypothesis  # noqa: E402

H = Hypothesis
CALM = {"replication_lag_s": 1.0}  # failover is safe
SEVERE_LAG = {"replication_lag_s": 15.0}  # validator blocks failover
MEDIUM_LAG = {"replication_lag_s": 8.0}  # failover allowed but risky


def belief(top: Hypothesis, p: float) -> dict:
    rest = (1.0 - p) / 3
    return {h: (p if h == top else rest) for h in H}


def test_confident_and_harmless_means_act():
    d = decide(belief(H.BAD_DEPLOY, 0.95), CALM, probes_used=0)
    assert d.kind == "act" and d.action == Action.ROLLBACK_DEPLOY


def test_harmless_actions_need_less_confidence_than_risky_ones():
    """At the same 80% confidence: rollback goes ahead, block_traffic does not."""
    assert decide(belief(H.BAD_DEPLOY, 0.80), CALM, 0).kind == "act"
    assert decide(belief(H.ATTACK, 0.80), CALM, 0).kind != "act"


def test_risky_action_acts_only_when_very_sure():
    assert decide(belief(H.ATTACK, 0.97), CALM, 0).kind == "act"


def test_uncertain_means_probe_first_then_ask_a_human():
    b = belief(H.ATTACK, 0.45)
    assert decide(b, CALM, probes_used=0).kind == "probe"
    assert decide(b, CALM, probes_used=DEFAULT_COSTS.max_probes).kind == "escalate"


def test_validator_blocked_fix_is_never_acted_on():
    for p in (0.6, 0.9, 0.999):
        d = decide(belief(H.DB_FAULT, p), SEVERE_LAG, probes_used=DEFAULT_COSTS.max_probes)
        assert d.kind == "escalate"
        assert d.options and d.options[0]["blocked_without_approval"] is True


def test_medium_lag_failover_is_risky_so_needs_more_confidence():
    assert decide(belief(H.DB_FAULT, 0.99), MEDIUM_LAG, 0).kind == "act"
    assert decide(belief(H.DB_FAULT, 0.70), MEDIUM_LAG, 0).kind != "act"


def test_falls_back_to_an_allowed_fix_when_the_top_one_is_blocked():
    """Top guess is db_fault (blocked); a confident second choice that is allowed can still be run."""
    b = {H.DB_FAULT: 0.05, H.BAD_DEPLOY: 0.93, H.ATTACK: 0.01, H.DEPENDENCY_TIMEOUT: 0.01}
    assert decide(b, SEVERE_LAG, 0).action == Action.ROLLBACK_DEPLOY


def test_decision_explains_itself_with_numbers():
    d = decide(belief(H.ATTACK, 0.45), CALM, 0)
    assert "expected cost" in d.reason and set(d.costs) >= {"act", "probe", "escalate"}


def test_costs_are_tunable():
    stingy = CostModel(human_cost=0.5)  # asking a human is nearly free
    assert decide(belief(H.ATTACK, 0.45), CALM, 0, stingy).kind == "escalate"


def test_escalation_options_shape_matches_what_the_console_reads():
    opts = escalation_options(belief(H.DB_FAULT, 0.6), SEVERE_LAG)
    assert [o["action"] for o in opts][-1] == "noop" and len(opts) == 4
    assert opts[0]["hypothesis"] == "db_fault" and opts[0]["blocked_without_approval"]
    assert all({"action", "hypothesis", "probability", "risk", "blocked_without_approval"} <= set(o) for o in opts)


def test_never_acts_on_a_long_shot_even_if_a_human_is_costly():
    """Regression: with an expensive human the rule once 'acted' on a ~1% fix instead of asking."""
    costly = CostModel(human_cost=8.0)
    b = {H.DB_FAULT: 0.96, H.BAD_DEPLOY: 0.01, H.ATTACK: 0.02, H.DEPENDENCY_TIMEOUT: 0.01}
    d = decide(b, SEVERE_LAG, probes_used=costly.max_probes, costs=costly)  # db failover is blocked
    assert d.kind == "escalate"
