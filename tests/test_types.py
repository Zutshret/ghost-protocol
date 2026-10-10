from shared.types import (
    AGENT_FEATURES,
    CORRECT_FIX,
    FEATURE_BASELINES,
    Action,
    Hypothesis,
    uniform_belief,
)


def test_every_hypothesis_has_a_fix():
    for h in Hypothesis:
        assert h in CORRECT_FIX
        assert CORRECT_FIX[h] in Action


def test_uniform_belief_sums_to_one():
    assert abs(sum(uniform_belief().values()) - 1.0) < 1e-9


def test_every_feature_has_a_baseline_and_one_owner():
    owners = {}
    for agent, features in AGENT_FEATURES.items():
        for f in features:
            assert f in FEATURE_BASELINES
            assert f not in owners, f"{f} is seen by two agents"
            owners[f] = agent
    assert set(owners) == set(FEATURE_BASELINES)
