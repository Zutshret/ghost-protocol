"""Mode D hands over to the agents the moment two runbook rules match."""

from backend.engine import IncidentEngine
from shared.types import Mode, MessageType


def _run(flag=None, seed=2):
    kw = {} if flag is None else {"escalate_on_conflict": flag}
    e = IncidentEngine("S2", "D", seed, use_llm=False, agents_mode_for_d=Mode.C, tick_delay=0, **kw)
    return e, e.run()


def test_default_hands_over_on_conflicting_rules_and_gets_s2_right():
    e, m = _run()
    triggers = [x.content.get("trigger", "") for x in e.bus.history if x.type == MessageType.MODE_SWITCH]
    assert any("runbook rules conflict" in t for t in triggers)
    assert m.correct_diagnosis and m.unnecessary_actions == 0


def test_naive_variant_still_reproduces_the_runbook_misfire():
    e, m = _run(flag=False)
    assert not m.correct_diagnosis and m.unnecessary_actions == 1


def test_default_is_on():
    assert IncidentEngine.__dataclass_fields__["escalate_on_conflict"].default is True
