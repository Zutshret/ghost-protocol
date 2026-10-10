"""AGNTCY light must be optional: off by default, and harmless when Docker/Directory is down."""

import json

import pytest

from agents import agntcy
from agents.agent_base import load_registry
from agents.recruitment import find_specialist
from backend.engine import IncidentEngine


@pytest.fixture(autouse=True)
def fresh_state(monkeypatch):
    monkeypatch.setattr(agntcy, "_cids", {})
    monkeypatch.setattr(agntcy, "_status", {"published": False, "directory": "not tried", "error": None})
    monkeypatch.setattr(agntcy, "_tracer", lambda: (None, None))  # never export spans in tests


def test_off_by_default(monkeypatch):
    monkeypatch.delenv("GHOST_AGNTCY", raising=False)
    assert not agntcy.enabled()
    assert agntcy.lookup("dependency_timeout_analysis") is None
    assert agntcy.publish_registry(load_registry().values()) == {}
    spec, where = find_specialist("dependency_timeout_analysis", set())
    assert spec.id == "network_analyst" and where == "registry.json lookup"


def test_card_uses_valid_oasf_names_and_keeps_capabilities():
    card = agntcy.card_for(load_registry()["network_analyst"])
    assert card["schema_version"] == "0.8.0"
    assert card["skills"] == [{"name": agntcy.OASF_SKILL}]
    assert "dependency_timeout_analysis" in card["annotations"]["ghost.capabilities"]
    assert card == agntcy.card_for(load_registry()["network_analyst"])  # deterministic -> stable CID


def test_docker_off_falls_back_to_registry_and_run_still_works(monkeypatch):
    monkeypatch.setenv("GHOST_AGNTCY", "1")
    monkeypatch.setenv("GHOST_DIRCTL", "definitely-not-a-real-dirctl-binary")
    e = IncidentEngine("S3", "B", 0)
    m = e.run()
    assert m.correct_diagnosis
    rec = [x for x in e.bus.history if x.type.value == "recruit" and not x.content["initial"]]
    assert rec and "registry.json lookup (AGNTCY Directory unavailable)" in rec[0].rationale
    assert e.bus.history[0].content["agntcy"]["directory"] == "unavailable"


def test_recruits_through_directory_when_available(monkeypatch):
    monkeypatch.setenv("GHOST_AGNTCY", "1")
    record = {"data": agntcy.card_for(load_registry()["network_analyst"])}

    def fake_dirctl(args, stdin=None):
        if args[0] == "push":
            return f"Pushed record with CID: cid-{json.loads(stdin)['annotations']['ghost.id']}\n"
        if args[0] == "search":
            return json.dumps([record])
        return None

    monkeypatch.setattr(agntcy, "_dirctl", fake_dirctl)
    assert agntcy.publish_registry(load_registry().values())["network_analyst"] == "cid-network_analyst"
    spec, where = find_specialist("dependency_timeout_analysis", set())
    assert spec.id == "network_analyst"
    assert where == "AGNTCY Directory search (record cid-network_analyst)"
