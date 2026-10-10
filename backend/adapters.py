"""One place that decides: Person A's real modules, or the stand-ins.

Everything comes from Person A's simulator/ and intelligence/ packages.
standins/ is kept only as a fallback: set GHOST_STANDINS=1 to force it
(useful for a safe demo or for tests that must not depend on tuning).
See docs/INTEGRATION.md.
"""

from __future__ import annotations

import os

from standins import intelligence as _si
from standins.sim import StandInSimulator, to_level

FORCE_STANDINS = os.getenv("GHOST_STANDINS") == "1"


def make_simulator():
    if not FORCE_STANDINS:
        try:
            from simulator.sim import Simulator  # type: ignore

            return Simulator(), "simulator.sim"
        except ImportError:
            pass
    return StandInSimulator(), "standins.sim"


def make_belief_engine():
    if not FORCE_STANDINS:
        try:
            from intelligence.beliefs import BeliefEngine  # type: ignore

            return BeliefEngine(), "intelligence.beliefs"
        except ImportError:
            pass
    return _si.StandInBeliefEngine(), "standins.intelligence"


def _real_or_standin(module: str, name: str, fallback):
    if not FORCE_STANDINS:
        try:
            return getattr(__import__(module, fromlist=[name]), name)
        except ImportError:
            pass
    return fallback


# Belief helpers (A5), decision rule (A6), runbook and validator (A3).
log_pool = _real_or_standin("intelligence.beliefs", "log_pool", _si.log_pool)
entropy = _real_or_standin("intelligence.beliefs", "entropy", _si.entropy)
brier = _real_or_standin("intelligence.beliefs", "brier", _si.brier)
failed_action_update = _real_or_standin("intelligence.beliefs", "failed_action_update", _si.failed_action_update)
decide = _real_or_standin("intelligence.decision", "decide", _si.decide)
escalation_options = _real_or_standin("intelligence.decision", "escalation_options", _si.escalation_options)
runbook_matches = _real_or_standin("simulator.runbook", "runbook_matches", _si.runbook_matches)
validate = _real_or_standin("simulator.validator", "validate", _si.validate)


def _pick_level_of():
    """Person A's simulator.faults.level_of keeps thresholds in sync with their simulator."""
    if not FORCE_STANDINS:
        try:
            from simulator.faults import level_of as real_level_of  # type: ignore

            return real_level_of
        except ImportError:
            pass
    return to_level


level_of = _pick_level_of()
