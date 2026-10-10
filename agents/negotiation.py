"""Peer negotiation, Mode C (B8). No central aggregator chooses the outcome.

Protocol, per round (max MAX_ROUNDS):
  1. Every agent posts a PROPOSAL (its own preferred action from its own belief
     and goal). Changed beliefs are re-posted as BELIEF messages.
  2. Every agent CHALLENGEs the most confident peer that disagrees with it,
     sharing its own strongest evidence and asking for the peer's. The peer
     replies with EVIDENCE from its own data. Both update via the belief engine.
  3. The most-supported proposals are put to a vote. Each agent votes ACCEPT,
     REJECT or VETO from its own belief and goal. A proposal passes with at
     least 2/3 ACCEPT and no VETO from a safety-critical agent. Risky actions
     (the validator flags them: failover_db, block_traffic) need everyone.
  4. No agreement after MAX_ROUNDS -> ESCALATE to a human (deadlock rule).
The only shared logic is the protocol (quorum + veto + round limit), which is
the same for everyone: there is no agent or component that pools beliefs.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Callable

from agents.agent_base import Agent, fmt_belief, top
from backend.adapters import validate
from shared.types import Action, Message, MessageType

MAX_ROUNDS = 4
QUORUM = 2 / 3
EVIDENCE_PER_REPLY = 2


@dataclass
class Outcome:
    kind: str  # "act" | "probe" | "escalate"
    action: Action
    reason: str
    provenance: list[int] = field(default_factory=list)
    votes: dict[str, str] = field(default_factory=dict)
    rounds: int = 0


def negotiate(
    agents: list[Agent],
    publish: Callable[[Message], Message],
    run_id: str,
    tick: int,
    state: dict[str, float],
    probes_used: int,
    max_probes: int = 2,
    speak: Callable | None = None,  # optional wording layer: speak(kind, facts, fallback, spec) -> str
) -> Outcome:
    trail: list[int] = []
    n = len(agents)
    need = math.ceil(QUORUM * n)
    last_post = {a.id: (top(a.belief)[0], top(a.belief)[1]) for a in agents}
    asked: set[tuple[str, str]] = set()
    last_votes: dict[str, str] = {}

    def post(m: Message) -> Message:
        m = publish(m)
        trail.append(m.id)
        return m

    for rnd in range(1, MAX_ROUNDS + 1):
        # 1. proposals (+ re-posted beliefs if they moved)
        proposals: dict[str, Action] = {}
        for a in agents:
            h, p = top(a.belief)
            ph, pp = last_post[a.id]
            if rnd > 1 and (h != ph or abs(p - pp) > 0.05):
                msg = a.belief_message(run_id, tick)
                msg.content["round"] = rnd
                msg.rationale = f"Round {rnd}: my view changed from {ph.value} {pp:.0%} to {h.value} {p:.0%} after peer evidence. " + a.why_preferred(a.preferred_action())
                post(msg)
                last_post[a.id] = (h, p)
            act = a.preferred_action()
            if act == Action.PROBE and probes_used >= max_probes:
                act = max(a.utilities(), key=a.utilities().get)
            proposals[a.id] = act
            post(Message(run_id=run_id, tick=tick, sender=a.id, type=MessageType.PROPOSAL,
                         content={"action": act.value, "round": rnd, "belief": fmt_belief(a.belief)},
                         rationale=a.why_preferred(act)))

        # 2. challenges and evidence replies
        for x in agents:
            hx, _ = top(x.belief)
            rivals = [y for y in agents if y is not x and proposals[y.id] != proposals[x.id]
                      and top(y.belief)[0] != hx and (x.id, y.id) not in asked]
            if not rivals:
                continue
            y = max(rivals, key=lambda r: top(r.belief)[1])
            asked.add((x.id, y.id))
            hy, py = top(y.belief)
            mine = {f: x.own_levels[f] for f in x.discriminating_features(hx, hy)[:EVIDENCE_PER_REPLY]}
            template = (f"@{y.id}: you say {hy.value} ({py:.0%}) but I see "
                        + (", ".join(f"{f} {l.value}" for f, l in mine.items()) or "nothing")
                        + f", which points to {hx.value}. What is your evidence?")
            words = template if speak is None else speak(
                "challenge",
                {"colleague": y.id, "my_hypothesis": hx.value, "their_hypothesis": hy.value,
                 "their_confidence_pct": round(py * 100), "my_evidence": {f: l.value for f, l in mine.items()}},
                template, x.spec)
            post(Message(run_id=run_id, tick=tick, sender=x.id, type=MessageType.CHALLENGE,
                         content={"target": y.id, "round": rnd, "my_hypothesis": hx.value,
                                  "their_hypothesis": hy.value, "my_evidence": {f: l.value for f, l in mine.items()}},
                         rationale=words))
            y_new = y.learn(x.id, mine)
            theirs = {f: y.own_levels[f] for f in y.discriminating_features(hy, hx)[:EVIDENCE_PER_REPLY]}
            x_new = x.learn(y.id, theirs)
            post(Message(run_id=run_id, tick=tick, sender=y.id, type=MessageType.EVIDENCE,
                         content={"to": x.id, "round": rnd, "evidence": {f: l.value for f, l in theirs.items()},
                                  "values": {f: y.obs.values.get(f) for f in theirs} if y.obs else {},
                                  "challenger_learned": list(x_new), "i_learned": list(y_new)},
                         rationale=(f"@{x.id}: from my own data, " + ", ".join(f"{f} is {l.value}" for f, l in theirs.items())
                                    if theirs else f"@{x.id}: I have no evidence to share (ablated).")))

        # 3. vote on the most-supported proposals (after everyone updated)
        for a in agents:
            act = a.preferred_action()
            if act == Action.PROBE and probes_used >= max_probes:
                act = max(a.utilities(), key=a.utilities().get)
            proposals[a.id] = act
        support: dict[Action, float] = {}
        for a in agents:
            support[proposals[a.id]] = support.get(proposals[a.id], 0) + 1 + top(a.belief)[1] / 10
        for cand in sorted(support, key=support.get, reverse=True)[:2]:
            votes: dict[str, str] = {}
            vetoes = []
            for a in agents:
                kind, why = a.vote(cand, state)
                votes[a.id] = kind.value
                if kind == MessageType.VETO:
                    vetoes.append(a.id)
                post(Message(run_id=run_id, tick=tick, sender=a.id, type=kind,
                             content={"action": cand.value, "round": rnd}, rationale=why))
            accepts = sum(v == MessageType.ACCEPT.value for v in votes.values())
            last_votes = votes
            quorum = n if validate(cand, state).risky else need
            if accepts >= quorum and not vetoes:
                kind = "probe" if cand == Action.PROBE else "act"
                return Outcome(kind, cand, f"round {rnd}: {accepts}/{n} accepted {cand.value} (needed {quorum}), no veto",
                               trail, votes, rnd)

    hy = {a.id: f"{top(a.belief)[0].value} {top(a.belief)[1]:.0%}" for a in agents}
    return Outcome("escalate", max(support, key=support.get),
                   f"no proposal reached {need}/{n} without a veto in {MAX_ROUNDS} rounds; positions: {hy}",
                   trail, last_votes, MAX_ROUNDS)
