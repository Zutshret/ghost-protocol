"""A6: the decision rule. Act, probe, or ask a human?

The idea, in plain words
------------------------
Instead of magic thresholds ("act if 90% sure"), compare what each choice is
expected to cost, in "ticks of pain" (one tick of ongoing incident = 1):

  ACT now on the best fix:   if we are wrong (chance 1 - p) we waste a whole hold
                             period before retrying, plus any extra damage the
                             action does when misapplied (locking out customers,
                             a risky database failover).
  PROBE first:               costs a tick, but the cleaner readings cut the chance of
                             being wrong in half (assumption: PROBE_GAIN).
  ASK a human:               costs a fixed delay while someone answers, but the
                             answer is right.

Pick the cheapest. Consequences that fall out naturally, without hard-coding:
- cheap, harmless actions (rollback, restart) are taken at modest confidence;
- risky actions (block traffic, failover) need high confidence;
- if the validator blocks the best action, acting is not an option at all;
- the safety validator always has the last word.

Every decision carries a plain-English reason with the numbers (shown in the console).

Same names and signatures as the stand-ins in Person B's `standins/intelligence.py`:
    decide(pooled, state, probes_used) -> Decision
    escalation_options(pooled, state) -> list[dict]
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.types import CORRECT_FIX, Action, Belief
from simulator.validator import validate


@dataclass(frozen=True)
class CostModel:
    """How bad each kind of mistake is, in ticks of pain. Tune these, not the code."""

    probe_cost: float = 1.0  # a probe costs one tick of waiting
    probe_gain: float = 0.5  # share of the chance-of-being-wrong a probe removes
    human_cost: float = 3.0  # delay while a human reads the options and answers
    retry_cost: float = 4.0  # a wrong action wastes the hold period before we retry
    risky_harm: float = 8.0  # extra damage if a RISKY action (block / failover) is wrong
    max_probes: int = 2


DEFAULT_COSTS = CostModel()
MAX_PROBES = DEFAULT_COSTS.max_probes


@dataclass
class Decision:
    kind: str  # "act" | "probe" | "escalate"
    action: Action
    confidence: float  # belief that `action` is the right fix
    reason: str
    options: list[dict] = field(default_factory=list)  # filled when escalating
    costs: dict[str, float] = field(default_factory=dict)  # expected cost of each choice (for the console)


def _loss_if_act(p_right: float, risky: bool, costs: CostModel) -> float:
    harm = costs.risky_harm if risky else 0.0
    return (1.0 - p_right) * (costs.retry_cost + harm)


def decide(
    pooled: Belief,
    state: dict[str, float],
    probes_used: int,
    costs: CostModel = DEFAULT_COSTS,
) -> Decision:
    """Choose the cheapest of: act on the best allowed fix, probe, or escalate."""
    ranked = sorted(pooled.items(), key=lambda kv: -kv[1])
    top_h, top_p = ranked[0]
    top_action = CORRECT_FIX[top_h]

    # Best fix that the safety validator lets us run without a human.
    best_act: tuple[float, Action, float, str] | None = None  # (loss, action, p, validator reason)
    for h, p in ranked:
        action = CORRECT_FIX[h]
        verdict = validate(action, state)
        if not verdict.allowed:
            continue
        loss = _loss_if_act(p, verdict.risky, costs)
        if best_act is None or loss < best_act[0]:
            best_act = (loss, action, p, verdict.reason)

    choices: dict[str, float] = {"escalate": costs.human_cost}
    if best_act is not None:
        choices["act"] = best_act[0]
    if probes_used < costs.max_probes:
        # After a probe we expect to act with (1 - gain) of today's risk of being wrong.
        reference = best_act[0] if best_act is not None else costs.human_cost
        choices["probe"] = costs.probe_cost + (1.0 - costs.probe_gain) * reference
    rounded = {k: round(v, 2) for k, v in choices.items()}
    summary = ", ".join(f"{k} {v:.1f}" for k, v in sorted(rounded.items(), key=lambda kv: kv[1]))

    # Cheapest wins; ties prefer acting, then probing, then asking.
    preference = {"act": 0, "probe": 1, "escalate": 2}
    kind = min(choices, key=lambda k: (choices[k], preference[k]))

    if kind == "act":
        _, action, p, why = best_act  # type: ignore[misc]
        return Decision("act", action, p, f"P({top_h.value})={top_p:.2f}; expected cost [{summary}] -> act; validator: {why}", costs=rounded)
    if kind == "probe":
        blocked = best_act is None or best_act[1] != top_action
        note = " (top fix is blocked by the validator)" if blocked and best_act is None else ""
        return Decision("probe", Action.PROBE, top_p, f"unsure: P({top_h.value})={top_p:.2f}{note}; expected cost [{summary}] -> probe first", costs=rounded)
    why = f"still unsure after {probes_used} probe(s)" if probes_used else "not sure enough"
    if best_act is None:
        why = f"the safe-to-run fixes are blocked by the validator ({validate(top_action, state).reason})"
    return Decision(
        "escalate",
        top_action,
        top_p,
        f"{why}; expected cost [{summary}] -> ask a human",
        escalation_options(pooled, state),
        costs=rounded,
    )


def escalation_options(pooled: Belief, state: dict[str, float]) -> list[dict]:
    """What to show a human: the three likeliest fixes (with risks), plus 'hold'."""
    options = []
    for h, p in sorted(pooled.items(), key=lambda kv: -kv[1])[:3]:
        action = CORRECT_FIX[h]
        verdict = validate(action, state)
        options.append(
            {
                "action": action.value,
                "hypothesis": h.value,
                "probability": round(p, 3),
                "risk": verdict.reason,
                "blocked_without_approval": not verdict.allowed,
            }
        )
    options.append(
        {
            "action": Action.NOOP.value,
            "hypothesis": None,
            "probability": None,
            "risk": "incident continues; errors keep hurting availability",
            "blocked_without_approval": False,
        }
    )
    return options


__all__ = ["CostModel", "DEFAULT_COSTS", "Decision", "MAX_PROBES", "decide", "escalation_options"]
