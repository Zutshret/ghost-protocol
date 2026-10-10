"""Agent base class (B3).

An agent has a name, role, goal and the features it can see. Each round it
observes ONLY its own data, turns it into evidence (LLM or measured levels),
asks the belief engine for probabilities, and proposes the action that best
fits its belief *and its own goal* (that is where goals compete).
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

from agents import evidence
from shared.types import CORRECT_FIX, Action, Belief, Hypothesis, Level, Message, MessageType, Observation, uniform_belief

REGISTRY_PATH = Path(__file__).with_name("registry.json")
FIX_VALUE = 10.0  # utility of fixing the incident
ACCEPT_MARGIN = 3.0  # accept a proposal if it is at most this much worse than my own
VETO_BELOW = 0.85  # safety-critical agents veto risky actions unless this sure


@dataclass
class AgentSpec:
    id: str
    name: str
    role: str
    goal: str
    features: list[str]
    capabilities: list[str]
    core: bool
    safety_critical: bool
    act_threshold: float
    action_cost: dict[str, float]
    color: str

    def public(self) -> dict:
        return {k: v for k, v in self.__dict__.items()}


def load_registry() -> dict[str, AgentSpec]:
    data = json.loads(REGISTRY_PATH.read_text(encoding="utf-8"))
    return {d["id"]: AgentSpec(**d) for d in data}


def find_by_capability(capability: str) -> list[AgentSpec]:
    return [s for s in load_registry().values() if capability in s.capabilities]


def fmt_belief(b: Belief) -> dict[str, float]:
    return {h.value: round(p, 4) for h, p in b.items()}


def top(b: Belief) -> tuple[Hypothesis, float]:
    h = max(b, key=b.get)
    return h, b[h]


@dataclass
class Agent:
    spec: AgentSpec
    engine: object  # BeliefEngineAPI
    use_llm: bool = False
    ablated: bool = False  # ablation test: this agent's evidence is removed
    obs: Observation | None = None
    own_levels: dict[str, Level] = field(default_factory=dict)
    learned: dict[str, dict[str, Level]] = field(default_factory=dict)  # peer id -> levels
    failed: list[Action] = field(default_factory=list)
    belief: Belief = field(default_factory=uniform_belief)
    evidence_belief: Belief = field(default_factory=uniform_belief)  # before failed-action penalties
    rationale: str = ""
    extraction_info: dict = field(default_factory=dict)

    @property
    def id(self) -> str:
        return self.spec.id

    # ----- perception -------------------------------------------------------
    def perceive(self, obs: Observation, failed_actions: list[Action]) -> None:
        self.obs = obs
        self.failed = list(failed_actions)
        self.learned = {}
        if self.ablated:
            self.own_levels, self.rationale, self.extraction_info = {}, "(ablated: evidence removed)", {"source": "ablated"}
        else:
            self.own_levels, self.rationale, self.extraction_info = evidence.extract(self.spec, obs, self.use_llm)
        self._recompute()

    def learn(self, peer_id: str, levels: dict[str, Level]) -> dict[str, Level]:
        """Incorporate a peer's evidence. Returns only what was new to me."""
        known = self.learned.setdefault(peer_id, {})
        new = {f: l for f, l in levels.items() if f not in known and f not in self.own_levels}
        known.update(new)
        if new:
            self._recompute()
        return new

    def _recompute(self) -> None:
        from backend.adapters import failed_action_update

        b = uniform_belief()
        if self.own_levels:
            b = self.engine.update(self.id, b, self.own_levels)
        for peer, levels in self.learned.items():
            if levels:
                b = self.engine.update(peer, b, levels)
        self.evidence_belief = b
        for a in self.failed:
            b = failed_action_update(b, a)
        self.belief = b

    # ----- preferences (competing goals) ------------------------------------
    def utilities(self) -> dict[Action, float]:
        u = {}
        for a in (Action.ROLLBACK_DEPLOY, Action.BLOCK_TRAFFIC, Action.FAILOVER_DB, Action.RESTART_SERVICE):
            p_fix = sum(p for h, p in self.belief.items() if CORRECT_FIX[h] == a)
            u[a] = FIX_VALUE * p_fix - self.spec.action_cost.get(a.value, 1.0)
        return u

    def preferred_action(self) -> Action:
        _, p = top(self.belief)
        if p < self.spec.act_threshold:
            return Action.PROBE
        u = self.utilities()
        return max(u, key=u.get)

    def why_preferred(self, action: Action) -> str:
        h, p = top(self.belief)
        if action == Action.PROBE:
            return f"I'm only {p:.0%} sure it's {h.value} (I need {self.spec.act_threshold:.0%}); let's probe first."
        cost = self.spec.action_cost.get(action.value, 1.0)
        return f"I lean {h.value} ({p:.0%}). {action.value} fits my goal ({self.spec.goal.split(';')[0].lower()}; my cost {cost:g})."

    # ----- negotiation ------------------------------------------------------
    def veto_reason(self, action: Action, state: dict[str, float]) -> str | None:
        if not self.spec.safety_critical:
            return None
        if self.id == "database" and action == Action.FAILOVER_DB:
            p = self.belief.get(Hypothesis.DB_FAULT, 0.0)
            if p < VETO_BELOW:
                return f"failover risks data consistency and I'm only {p:.0%} sure the database is at fault"
        if self.id == "gateway" and action == Action.BLOCK_TRAFFIC:
            p = self.belief.get(Hypothesis.ATTACK, 0.0)
            if p < VETO_BELOW:
                return f"blocking would lock out real customers and I'm only {p:.0%} sure this is an attack"
        return None

    def vote(self, action: Action, state: dict[str, float]) -> tuple[MessageType, str]:
        veto = self.veto_reason(action, state)
        if veto:
            return MessageType.VETO, veto
        mine = self.preferred_action()
        if action == mine:
            return MessageType.ACCEPT, "matches my own proposal"
        if action == Action.PROBE:
            _, p = top(self.belief)
            if p < self.spec.act_threshold + 0.15:
                return MessageType.ACCEPT, f"more data is fine; I'm {p:.0%} sure"
            return MessageType.REJECT, f"I'm already {p:.0%} sure; probing wastes time"
        u = self.utilities()
        best = max(u.values())
        if u[action] >= best - ACCEPT_MARGIN:
            return MessageType.ACCEPT, f"acceptable to me (utility {u[action]:.1f} vs my best {best:.1f})"
        return MessageType.REJECT, f"poor fit for my belief/goal (utility {u[action]:.1f} vs my best {best:.1f})"

    def discriminating_features(self, mine: Hypothesis, theirs: Hypothesis) -> list[str]:
        """Which of MY features best separate two hypotheses (what a challenger asks for)."""
        import math

        def score(f: str) -> float:
            b = self.engine.update(self.id, uniform_belief(), {f: self.own_levels[f]})
            return abs(math.log(max(b[mine], 1e-9)) - math.log(max(b[theirs], 1e-9)))

        return sorted(self.own_levels, key=score, reverse=True)

    # ----- messages ---------------------------------------------------------
    def belief_message(self, run_id: str, tick: int) -> Message:
        h, p = top(self.belief)
        action = self.preferred_action()
        return Message(
            run_id=run_id, tick=tick, sender=self.id, type=MessageType.BELIEF,
            content={
                "belief": fmt_belief(self.belief),
                "evidence": {f: l.value for f, l in self.own_levels.items()},
                "values": dict(self.obs.values) if self.obs and not self.ablated else {},
                "learned_from": {k: {f: l.value for f, l in v.items()} for k, v in self.learned.items()},
                "preferred_action": action.value,
                "top": h.value, "confidence": round(p, 4),
                "evidence_source": self.extraction_info.get("source"),
                "llm_disagreed": self.extraction_info.get("llm_disagreed", []),
            },
            rationale=f"{self.rationale} {self.why_preferred(action)}".strip(),
        )
