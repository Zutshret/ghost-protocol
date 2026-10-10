"""Tests for Person B's parts: bus, agents, negotiation, engine (run on the stand-ins)."""

import os

os.environ["GHOST_STANDINS"] = "1"
os.environ["LLM_OFFLINE"] = "1"

from agents.agent_base import Agent, load_registry  # noqa: E402
from agents.bus import InMemoryBus  # noqa: E402
from agents.negotiation import negotiate  # noqa: E402
from backend.engine import IncidentEngine  # noqa: E402
from shared.types import Action, Hypothesis, Level, Message, MessageType, Mode  # noqa: E402
from standins.intelligence import StandInBeliefEngine  # noqa: E402
from standins.sim import StandInSimulator  # noqa: E402

import pytest  # noqa: E402

from backend import adapters  # noqa: E402
from standins import intelligence as si  # noqa: E402
from standins.sim import to_level  # noqa: E402


@pytest.fixture(autouse=True)
def use_standins(monkeypatch):
    """Run on the stand-ins whatever order the test files load in (the env var alone is
    too late if another test file imported the backend first)."""
    import agents.negotiation as negotiation

    monkeypatch.setattr(adapters, "FORCE_STANDINS", True)
    for name in ("log_pool", "entropy", "brier", "failed_action_update", "decide",
                 "escalation_options", "runbook_matches", "validate"):
        monkeypatch.setattr(adapters, name, getattr(si, name))
    monkeypatch.setattr(adapters, "level_of", to_level)
    monkeypatch.setattr(negotiation, "validate", si.validate)


def test_bus_publish_subscribe_and_topics():
    bus, got_all, got_veto = InMemoryBus(), [], []
    bus.subscribe(got_all.append)
    bus.subscribe(got_veto.append, topic="veto")
    bus.publish(Message(run_id="r", tick=0, sender="a", type=MessageType.BELIEF))
    bus.publish(Message(run_id="r", tick=0, sender="b", type=MessageType.VETO))
    assert [m.id for m in got_all] == [1, 2]
    assert [m.sender for m in got_veto] == ["b"]


def test_registry_has_five_core_agents_and_a_specialist():
    reg = load_registry()
    assert sum(s.core for s in reg.values()) == 5
    assert "dependency_timeout_analysis" in reg["network_analyst"].capabilities


def _team(scenario, seed, ticks=8):
    sim, eng = StandInSimulator(), StandInBeliefEngine()
    sim.reset(scenario, seed)
    for _ in range(ticks):
        sim.step(Action.NOOP)
    reg = load_registry()
    team = [Agent(reg[i], eng) for i in ["gateway", "payments", "database", "security", "deployment"]]
    for a in team:
        a.perceive(sim.observe(a.id), [])
    return sim, team


def test_agents_see_only_their_own_features():
    _, team = _team("S1", 0)
    for a in team:
        assert set(a.own_levels) == set(a.spec.features)


def test_database_vetoes_failover_when_unsure():
    _, team = _team("S2", 0)
    db = next(a for a in team if a.id == "database")
    kind, _ = db.vote(Action.FAILOVER_DB, {})
    assert kind == MessageType.VETO


def test_s2_peers_agree_on_rollback_without_aggregator():
    sim, team = _team("S2", 1)  # seed 1 has the attack decoy
    bus = InMemoryBus()
    out = negotiate(team, bus.publish, "t", sim.tick, sim.state, probes_used=0)
    assert out.kind == "act" and out.action == Action.ROLLBACK_DEPLOY
    assert any(m.type == MessageType.CHALLENGE for m in bus.history)


def test_new_evidence_changes_a_position():
    _, team = _team("S2", 1)
    sec = next(a for a in team if a.id == "security")
    dep = next(a for a in team if a.id == "deployment")
    before = sec.belief[Hypothesis.BAD_DEPLOY]
    sec.learn("deployment", dep.own_levels)
    assert sec.belief[Hypothesis.BAD_DEPLOY] > before


def test_same_seed_same_run():
    a = IncidentEngine("S2", Mode.C, 3).run()
    b = IncidentEngine("S2", Mode.C, 3).run()
    assert a == b


def test_s5_escalates_to_human_and_s1_does_not():
    assert IncidentEngine("S5", Mode.B, 2).run().escalated_to_human
    assert not IncidentEngine("S1", Mode.B, 2).run().escalated_to_human


def test_s3_recruits_network_analyst_with_reason():
    e = IncidentEngine("S3", Mode.B, 0)
    e.run()
    rec = [m for m in e.bus.history if m.type == MessageType.RECRUIT and m.content["agent"] == "network_analyst"]
    assert rec and "dependency_timeout" in rec[0].rationale


def test_runbook_misfires_on_s2_decoy_and_hybrid_switches_to_agents():
    a = IncidentEngine("S2", Mode.A, 1).run()
    assert not a.correct_diagnosis and a.unnecessary_actions >= 1
    d = IncidentEngine("S2", Mode.D, 1)
    m = d.run()
    assert any(x.type == MessageType.MODE_SWITCH and x.content.get("mode") == "agents" for x in d.bus.history)
    assert m.recovery_time < 30
