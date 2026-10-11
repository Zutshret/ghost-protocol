"""Confirmation round (step 2b): a doubtful safety-critical agent asks agreeing peers for evidence."""

import agents.negotiation as ng
from backend.engine import IncidentEngine
from shared.types import MessageType


def _run(seed: int):
    e = IncidentEngine("S1", "C", seed, use_llm=False, tick_delay=0)
    return e, e.run()


def test_s1_seed_that_used_to_deadlock_now_resolves_without_a_human():
    # seed 14: all five agents say db_fault, Database is at 69% (< 85% veto bar)
    e, m = _run(14)
    assert not m.escalated_to_human and m.correct_diagnosis
    kinds = [x.content.get("kind") for x in e.bus.history if x.type == MessageType.CHALLENGE]
    assert "confirm" in kinds


def test_without_confirmation_that_seed_still_deadlocks(monkeypatch):
    monkeypatch.setattr(ng, "CONFIRMATION", False)
    _, m = _run(14)
    assert m.escalated_to_human


def test_block_traffic_veto_is_never_relaxed():
    assert ng.CONFIRMABLE == {ng.Action.FAILOVER_DB}
