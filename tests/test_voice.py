"""Tests for the LLM voice layer: it may change wording, never decisions."""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest  # noqa: E402

from agents import llm, voice  # noqa: E402
from backend.engine import IncidentEngine  # noqa: E402

FACTS = {"colleague": "security", "my_hypothesis": "bad_deploy", "their_hypothesis": "attack",
         "their_confidence_pct": 62, "my_evidence": {"canary_error_rate": "high"}}
FALLBACK = "template text"


@pytest.fixture
def fake_llm(monkeypatch):
    """Pretend an LLM is configured and answers with whatever `reply[0]` says."""
    reply = ["I think it is a bad deploy; you say attack at 62%, but canary_error_rate is high."]
    monkeypatch.setattr(voice, "llm_available", lambda: True)

    def fake_ask(prompt, schema, system="", max_tokens=0):
        if schema is voice.Line:
            return voice.Line(text=reply[0])
        return None  # per-agent evidence extraction: fall back to measured levels

    monkeypatch.setattr(voice, "ask_json", fake_ask)
    monkeypatch.setattr("agents.evidence.ask_json", fake_ask)
    return reply


def test_template_used_when_llm_is_off(fake_llm):
    assert voice.say("challenge", FACTS, FALLBACK, use_llm=False) == FALLBACK


def test_template_used_when_no_key(monkeypatch):
    monkeypatch.setattr(voice, "llm_available", lambda: False)
    assert voice.say("challenge", FACTS, FALLBACK) == FALLBACK


def test_faithful_llm_text_is_used(fake_llm):
    assert voice.say("challenge", FACTS, FALLBACK) == fake_llm[0]


def test_invented_number_is_rejected(fake_llm):
    fake_llm[0] = "You say attack at 90%, but I am sure it is a bad deploy."
    assert voice.say("challenge", FACTS, FALLBACK) == FALLBACK


def test_invented_cause_or_action_is_rejected(fake_llm):
    fake_llm[0] = "This looks like a db_fault, we should failover_db."
    assert voice.say("challenge", FACTS, FALLBACK) == FALLBACK


def test_empty_or_rambling_text_is_rejected(fake_llm):
    fake_llm[0] = ""
    assert voice.say("challenge", FACTS, FALLBACK) == FALLBACK
    fake_llm[0] = "word " * 200
    assert voice.say("challenge", FACTS, FALLBACK) == FALLBACK


def test_unknown_kind_uses_template(fake_llm):
    assert voice.say("nonsense", FACTS, FALLBACK) == FALLBACK


def test_faithful_helper_directly():
    assert voice.faithful("62% sure it is a bad deploy", FACTS)
    assert not voice.faithful("63% sure", FACTS)
    assert not voice.faithful("the database is failing: db fault", FACTS)


@pytest.mark.parametrize("scenario,mode,seed", [("S2", "C", 2), ("S5", "B", 1), ("S5", "C", 1)])
def test_llm_changes_words_not_decisions(fake_llm, scenario, mode, seed):
    """Same incident with the LLM off and on: identical actions and outcomes."""
    off = IncidentEngine(scenario, mode, seed, use_llm=False)
    m_off = off.run()
    on = IncidentEngine(scenario, mode, seed, use_llm=True)
    m_on = on.run()
    assert [a.value for a in on.applied] == [a.value for a in off.applied]
    assert m_on.escalated_to_human == m_off.escalated_to_human
    assert m_on.recovery_time == m_off.recovery_time
    assert m_on.correct_diagnosis == m_off.correct_diagnosis
    # and the LLM-on run adds an end-of-run summary that the LLM-off run does not
    assert any(x.content.get("event") == "summary" for x in on.bus.history)
    assert not any(x.content.get("event") == "summary" for x in off.bus.history)


def test_llm_helper_throttle_and_rate_limit_parsing():
    class Boom(Exception):
        pass

    assert llm._rate_limit_delay(Boom("network down")) is None
    assert llm._rate_limit_delay(Boom('429 quota... Please retry in 34.5s.')) == pytest.approx(35.5)
    assert llm._rate_limit_delay(Boom("RESOURCE_EXHAUSTED")) == 20.0
