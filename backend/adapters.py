"""One place that decides: Person A's real modules, or the stand-ins.

When Person A pushes simulator/sim.py (class Simulator) and
intelligence/beliefs.py (class BeliefEngine), they are used automatically.
Set GHOST_STANDINS=1 to force the stand-ins (useful for a safe demo).
See docs/INTEGRATION.md for the exact names expected.
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


# Pooling, decision rule, runbook and validator: stand-ins until Person A's
# versions exist. Swap these imports for the real ones in one line each.
log_pool = _si.log_pool
entropy = _si.entropy
brier = _si.brier
failed_action_update = _si.failed_action_update
runbook_matches = _si.runbook_matches
validate = _si.validate
decide = _si.decide
escalation_options = _si.escalation_options
level_of = to_level
