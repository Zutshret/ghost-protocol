"""Safety validator (task A3).

Plain code (no AI) that checks an action against hard safety rules BEFORE it
runs. Both the runbook and the agent team go through it.

Three possible answers (a `Verdict`):
- allowed=True,  risky=False -> safe, go ahead.
- allowed=True,  risky=True  -> allowed, but has a downside; agents need more
                                confidence (or a human) before choosing it.
- allowed=False              -> blocked unless a human approves.

Same signature as the stand-in used by Person B's backend:
    validate(action, state, human_approved=False) -> Verdict
`state` is a dict of feature values (for example the latest readings).
"""

from __future__ import annotations

from dataclasses import dataclass

from shared.types import Action
from simulator.sim import Simulator

# A database failover while the replica is far behind can lose data.
RISKY_LAG_S = 5.0  # above this, failover is allowed but risky
HARD_BLOCK_LAG_S = Simulator.CONSISTENCY_LAG_LIMIT  # above this, failover is blocked (12 s)


@dataclass(frozen=True)
class Verdict:
    allowed: bool
    risky: bool
    reason: str


def validate(action: Action, state: dict[str, float], human_approved: bool = False) -> Verdict:
    action = Action(action)

    if action == Action.FAILOVER_DB:
        lag = float(state.get("replication_lag_s", 0.0))
        if lag > HARD_BLOCK_LAG_S:
            if human_approved:
                return Verdict(True, True, f"replication lag {lag:.1f}s is above the safe limit; a human accepted the risk")
            return Verdict(
                False,
                True,
                f"replication lag {lag:.1f}s > {HARD_BLOCK_LAG_S:.0f}s: failover would risk a consistency violation",
            )
        if lag > RISKY_LAG_S:
            return Verdict(True, True, f"replication lag {lag:.1f}s: failover risks data consistency")
        return Verdict(True, False, "safe")

    if action == Action.BLOCK_TRAFFIC:
        return Verdict(True, True, "can lock out real customers")

    return Verdict(True, False, "safe")
