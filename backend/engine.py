"""Incident engine: runs one scenario in one mode and publishes everything to the bus.

Used by the FastAPI backend (live, with a human in the loop) and by evaluation
scripts (fast, with a scripted human). Modes:
  A  runbook only                    C  agents negotiate peer to peer
  B  agents + central aggregator     D  runbook first; agents when the router says so
"""

from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from typing import Callable

from agents.agent_base import Agent, fmt_belief, load_registry, top
from agents.bus import InMemoryBus
from agents.llm import llm_calls
from agents.negotiation import Outcome, negotiate
from agents.recruitment import recruitment_needed, select_initial_team
from backend import adapters as ad
from shared.types import (
    AGENT_IDS, CORRECT_FIX, Action, Belief, Hypothesis, Level, Message, MessageType,
    Mode, Observation, RunMetrics, ScenarioId, uniform_belief,
)

RUN_TICKS = 30
FAULT_TICK = 5
VERIFY_TICKS = 4  # ticks to wait before judging whether a fix is helping
DETECT_TICKS = 3
HOLD_TICKS = 4  # after a human rejects, watch this long before re-deliberating
MAX_PROBES = 2

Human = Callable[[dict, "IncidentEngine"], dict]

SERVICE_FEATURES = {
    "gateway": ["edge_error_rate", "upstream_timeouts", "request_rate"],
    "auth": ["failed_logins", "suspicious_sources", "traffic_anomaly"],
    "payments": ["payment_error_rate", "queue_depth", "latency_ms"],
    "database": ["replication_lag_s", "slow_queries", "lock_waits"],
    "cache": ["conn_pool_saturation", "downstream_p99_ms"],
}


def oracle_human(content: dict, engine: "IncidentEngine") -> dict:
    """Scripted human for evaluation: approves the correct fix if it is offered."""
    want = CORRECT_FIX[engine.true_fault].value
    if any(o["action"] == want for o in content.get("options", [])):
        return {"decision": "approve", "action": want, "note": "oracle human (eval)"}
    return {"decision": "reject", "action": "noop", "note": "oracle human (eval)"}


def lockout(state: dict[str, float]) -> float:
    return state.get("customer_lockout", state.get("lockout_penalty", 0.0))


def badness(state: dict[str, float]) -> float:
    err = state.get("error_rate", max(state.get("edge_error_rate", 0), state.get("payment_error_rate", 0)))
    return max(err / 0.02, state.get("latency_ms", 0) / 300)


@dataclass
class IncidentEngine:
    scenario: ScenarioId
    mode: Mode
    seed: int = 0
    bus: InMemoryBus = field(default_factory=InMemoryBus)
    use_llm: bool = False
    human: Human = oracle_human
    tick_delay: float = 0.0
    agents_mode_for_d: Mode = Mode.B
    escalate_on_conflict: bool = False
    ablate: str | None = None
    run_id: str = field(default_factory=lambda: uuid.uuid4().hex[:8])
    should_stop: Callable[[], bool] = lambda: False

    def __post_init__(self) -> None:
        self.scenario, self.mode = ScenarioId(self.scenario), Mode(self.mode)
        self.sim, self.sim_source = ad.make_simulator()
        self.beliefs, self.belief_source = ad.make_belief_engine()
        self.registry = load_registry()

    # ------------------------------------------------------------------ util
    def publish(self, type: MessageType, sender: str, content: dict | None = None, rationale: str = "") -> Message:
        return self.bus.publish(Message(run_id=self.run_id, tick=self.tick, sender=sender, type=type,
                                        content=content or {}, rationale=rationale))

    def _observe(self, agent_id: str) -> Observation:
        try:
            return self.sim.observe(agent_id)
        except (KeyError, ValueError):
            # Real simulator doesn't know this (recruited) agent: build from raw state.
            feats = [f for f in self.registry[agent_id].features if f in self.state]
            values = {f: self.state[f] for f in feats}
            return Observation(agent_id=agent_id, tick=self.tick, values=values,
                               levels={f: ad.level_of(f, v) for f, v in values.items()})

    def _all_levels(self) -> dict[str, Level]:
        levels: dict[str, Level] = {}
        for a in AGENT_IDS:
            levels.update(self._observe(a).levels)
        return levels

    def _services(self) -> dict:
        out = {}
        for svc, feats in SERVICE_FEATURES.items():
            levels = {}
            for f in feats:
                if f in self.state:
                    try:
                        levels[f] = ad.level_of(f, self.state[f])
                    except KeyError:
                        pass
            if svc == "auth" and lockout(self.state) > 0:
                levels["customer_lockout"] = Level.HIGH
            n_high = sum(l == Level.HIGH for l in levels.values())
            n_med = sum(l == Level.MEDIUM for l in levels.values())
            health = "red" if n_high >= 1 and (n_high + n_med) >= 2 else "yellow" if n_high or n_med else "green"
            out[svc] = {"health": health, "levels": {f: l.value for f, l in levels.items()},
                        "values": {f: round(self.state[f], 4) for f in feats if f in self.state}}
        return out

    # ------------------------------------------------------------------- run
    def run(self) -> RunMetrics:
        self.sim.reset(self.scenario, self.seed)
        self.true_fault: Hypothesis = Hypothesis(getattr(self.sim, "true_fault"))
        self.tick = 0
        self.state: dict[str, float] = dict(getattr(self.sim, "state", {}) or {})
        self.phase = "monitoring"  # monitoring | runbook | agents | resolved
        self.team: list[Agent] = []
        self.failed: list[Action] = []
        self.tried: set[Action] = set()
        self.applied: list[Action] = []
        self.verifying: tuple[Action, int, float] | None = None
        self.hold_until = -1
        self.probes_used = 0
        self.escalated = False
        self.decision_belief: Belief | None = None
        self.last_belief: Belief | None = None
        self.recovered_at: int | None = None
        self.said: set[str] = set()
        self.bad_hist: list[float] = []  # badness per tick (detection + fix verification)
        llm0 = llm_calls()
        avail: list[float] = []

        self.publish(MessageType.TELEMETRY, "system", {
            "event": "start", "scenario": self.scenario.value, "mode": self.mode.value, "seed": self.seed,
            "simulator": self.sim_source, "belief_engine": self.belief_source, "use_llm": self.use_llm,
            "roster": [s.public() for s in self.registry.values()], "services": self._services(),
            "ablate": self.ablate,
        }, f"Run {self.run_id}: scenario {self.scenario.value}, mode {self.mode.value}, seed {self.seed}")

        for _ in range(RUN_TICKS):
            if self.should_stop():
                break
            action = Action.NOOP
            self.human_approved = False
            if self.phase not in ("resolved",):
                action = self._decide()
            self.state = dict(self._step(action))
            self.tick = getattr(self.sim, "tick", self.tick + 1)
            err = self.state.get("error_rate", max(self.state.get("edge_error_rate", 0), self.state.get("payment_error_rate", 0)))
            avail.append(max(0.0, 1 - err - lockout(self.state)))
            if self.recovered_at is None and self.phase != "monitoring" and self.sim.is_recovered():
                self.recovered_at = self.tick
                self.phase, self.verifying = "resolved", None
                self.publish(MessageType.MODE_SWITCH, "router", {"mode": "resolved"},
                             f"Recovered: errors < 2% and latency < 300 ms for 3 ticks (tick {self.tick}).")
            self.publish(MessageType.TELEMETRY, "simulator", {
                "phase": self.phase, "services": self._services(), "availability": avail[-1],
                "error_rate": round(err, 4), "latency_ms": round(self.state.get("latency_ms", 0), 1),
                "lockout": lockout(self.state),
            })
            if self.tick_delay:
                time.sleep(self.tick_delay)

        correct = CORRECT_FIX[self.true_fault]
        real = [a for a in self.applied if a not in (Action.PROBE, Action.NOOP)]
        final_b = self.decision_belief or self.last_belief
        metrics = RunMetrics(
            scenario=self.scenario, mode=self.mode, seed=self.seed, true_fault=self.true_fault,
            recovery_time=min(RUN_TICKS, (self.recovered_at - FAULT_TICK) if self.recovered_at else RUN_TICKS),
            availability=round(sum(avail) / max(1, len(avail)), 4),
            unnecessary_actions=sum(a != correct for a in real),
            correct_diagnosis=bool(real) and real[0] == correct,
            escalated_to_human=self.escalated,
            brier_score=round(ad.brier(final_b, self.true_fault), 4) if final_b else None,
            llm_calls=llm_calls() - llm0,
        )
        self.publish(MessageType.TELEMETRY, "system", {"event": "end", "metrics": metrics.model_dump(mode="json")},
                     f"Run finished. Recovery {metrics.recovery_time} ticks, availability {metrics.availability:.1%}, "
                     f"unnecessary actions {metrics.unnecessary_actions}, correct diagnosis {metrics.correct_diagnosis}.")
        return metrics

    def _step(self, action: Action) -> dict[str, float]:
        if self.human_approved:
            try:  # Person A's simulator records that a human accepted the risk
                return self.sim.step(action, approved=True)
            except TypeError:
                pass
        return self.sim.step(action)

    # -------------------------------------------------------------- routing
    def _decide(self) -> Action:
        if self.state:
            self.bad_hist.append(badness(self.state))
        if self.phase == "monitoring":
            # several bad ticks in a row, so flaky readings are not an incident
            if len(self.bad_hist) >= DETECT_TICKS and min(self.bad_hist[-DETECT_TICKS:]) > 1.5:
                to = "runbook" if self.mode in (Mode.A, Mode.D) else "agents"
                self.phase = to
                self.publish(MessageType.MODE_SWITCH, "router", {"mode": to, "trigger": "incident_detected"},
                             f"Incident detected (error {self.state.get('error_rate', 0):.1%}, latency "
                             f"{self.state.get('latency_ms', 0):.0f} ms). Handing to the {'runbook' if to == 'runbook' else 'agent team'}.")
            else:
                return Action.NOOP

        if self.verifying:
            act, t0, _ = self.verifying
            waited = self.tick - t0
            peak = max(self.bad_hist)
            now = min(self.bad_hist[-2:])  # robust to one flaky tick
            if waited < VERIFY_TICKS or now < 0.5 * peak:  # improving: keep waiting for recovery
                return Action.NOOP
            self.verifying = None
            self.failed.append(act)
            self.publish(MessageType.EVIDENCE, "router", {"failed_action": act.value, "waited": waited},
                         f"{act.value} did not help after {waited} ticks: evidence against what it fixes.")
            if self.phase == "runbook" and self.mode == Mode.D:
                self._switch_to_agents(f"the runbook's fix ({act.value}) did not help within {waited} ticks")

        if self.tick < self.hold_until:
            return Action.NOOP
        if self.phase == "runbook":
            return self._runbook_step()
        return self._agents_step()

    def _switch_to_agents(self, reason: str) -> None:
        self.phase = "agents"
        self.publish(MessageType.MODE_SWITCH, "router", {"mode": "agents", "trigger": reason},
                     f"Switching from runbook (deterministic) to agents (probabilistic): {reason}.")

    def _say_once(self, key: str, type: MessageType, sender: str, content: dict, rationale: str) -> None:
        if key not in self.said:
            self.said.add(key)
            self.publish(type, sender, content, rationale)

    # ------------------------------------------------------------- runbook
    def _runbook_step(self) -> Action:
        levels = self._all_levels()
        matches = [r for r in ad.runbook_matches(levels) if r.action not in self.tried]
        if not matches:
            if self.mode == Mode.D:
                self._switch_to_agents("no runbook rule matches the symptoms")
                return self._agents_step()
            self._say_once("norule", MessageType.PROPOSAL, "runbook", {"action": "noop"},
                           "No runbook rule matches; waiting.")
            return Action.NOOP
        if len(matches) > 1 and self.mode == Mode.D and self.escalate_on_conflict:
            self._switch_to_agents(f"runbook rules conflict: {', '.join(r.name for r in matches)}")
            return self._agents_step()
        rule = matches[0]
        conflict = f" (also matched: {', '.join(r.name for r in matches[1:])}; first rule wins)" if len(matches) > 1 else ""
        p = self.publish(MessageType.PROPOSAL, "runbook",
                         {"action": rule.action.value, "rule": rule.name, "matched": [r.name for r in matches],
                          "levels": {f: l.value for f, l in levels.items()}},
                         f"Rule '{rule.name}': {rule.when} -> {rule.action.value}{conflict}.")
        self.tried.add(rule.action)
        verdict = ad.validate(rule.action, self.state)
        if not verdict.allowed:
            self.publish(MessageType.VETO, "validator", {"action": rule.action.value}, f"Blocked: {verdict.reason}.")
            if self.mode == Mode.D:
                self._switch_to_agents(f"validator blocked the runbook's {rule.action.value}")
            return Action.NOOP
        if self.decision_belief is None:
            h = next(h for h, a in CORRECT_FIX.items() if a == rule.action)
            self.decision_belief = {x: 1.0 if x == h else 0.0 for x in Hypothesis}
        return self._apply(rule.action, "runbook", [p.id], f"Runbook applies {rule.action.value}. Validator: {verdict.reason}.")

    def _apply(self, action: Action, sender: str, provenance: list[int], rationale: str) -> Action:
        self.publish(MessageType.ACTION, sender, {"action": action.value, "provenance": provenance}, rationale)
        self.applied.append(action)
        if action not in (Action.PROBE, Action.NOOP):
            self.verifying = (action, self.tick, badness(self.state))
        return action

    # -------------------------------------------------------------- agents
    def _form_team(self) -> None:
        levels = self._all_levels()
        for spec, why in select_initial_team(levels):
            self.team.append(Agent(spec, self.beliefs, use_llm=self.use_llm, ablated=(spec.id == self.ablate)))
            self.publish(MessageType.RECRUIT, "router", {"agent": spec.id, "capabilities": spec.capabilities, "initial": True},
                         f"Selected {spec.name}: {why}.")

    def _agents_step(self) -> Action:
        if not self.team:
            self._form_team()
        trail: list[int] = []
        for agent in self.team:
            agent.perceive(self._observe(agent.id), self.failed)
            trail.append(self.bus.publish(agent.belief_message(self.run_id, self.tick)).id)

        rec = recruitment_needed([a.evidence_belief for a in self.team], {a.id for a in self.team})
        if rec:
            spec, why = rec
            agent = Agent(spec, self.beliefs, use_llm=self.use_llm, ablated=(spec.id == self.ablate))
            self.team.append(agent)
            trail.append(self.publish(MessageType.RECRUIT, "router",
                                      {"agent": spec.id, "capabilities": spec.capabilities, "initial": False},
                                      f"Recruited {spec.name} mid-incident: {why}.").id)
            agent.perceive(self._observe(agent.id), self.failed)
            trail.append(self.bus.publish(agent.belief_message(self.run_id, self.tick)).id)

        negotiating = self.mode == Mode.C or (self.mode == Mode.D and self.agents_mode_for_d == Mode.C)
        if negotiating:
            out = negotiate(self.team, self.bus.publish, self.run_id, self.tick, self.state,
                            self.probes_used, MAX_PROBES)
            out.provenance = trail + out.provenance
            sender = "team"
            group = _mean([a.belief for a in self.team])  # for display / Brier only, not for deciding
        else:
            pooled = ad.log_pool([a.evidence_belief for a in self.team])
            for f in self.failed:
                pooled = ad.failed_action_update(pooled, f)
            d = ad.decide(pooled, self.state, self.probes_used)
            p = self.publish(MessageType.PROPOSAL, "aggregator",
                             {"action": d.action.value, "decision": d.kind, "pooled": fmt_belief(pooled),
                              "entropy": round(ad.entropy(pooled), 3), "provenance": trail},
                             f"Pooled belief: {top(pooled)[0].value} {top(pooled)[1]:.0%} "
                             f"(entropy {ad.entropy(pooled):.2f} bits). Decision: {d.kind} - {d.reason}.")
            out = Outcome(d.kind, d.action, d.reason, trail + [p.id])
            sender, group = "aggregator", pooled
        self.last_belief = group

        if out.kind == "probe":
            self.probes_used += 1
            return self._apply(Action.PROBE, sender, out.provenance,
                               f"Probe {self.probes_used}/{MAX_PROBES}: {out.reason}. Costs one tick, gives cleaner readings.")
        if out.kind == "act":
            verdict = ad.validate(out.action, self.state)
            if verdict.allowed:
                if self.decision_belief is None:
                    self.decision_belief = group
                return self._apply(out.action, sender, out.provenance,
                                   f"{'Agreed' if negotiating else 'Aggregator chose'} {out.action.value}: {out.reason}. "
                                   f"Validator: {verdict.reason}.")
            self.publish(MessageType.VETO, "validator", {"action": out.action.value}, f"Blocked: {verdict.reason}.")
            out = Outcome("escalate", out.action, f"validator blocked {out.action.value}", out.provenance)
        return self._escalate(group, out)

    def _escalate(self, belief: Belief, out: Outcome) -> Action:
        self.escalated = True
        options = ad.escalation_options(belief, self.state)
        esc = self.publish(MessageType.ESCALATE, "team" if self.mode != Mode.B else "aggregator", {
            "options": options, "reason": out.reason, "belief": fmt_belief(belief),
            "agents": {a.id: fmt_belief(a.belief) for a in self.team}, "provenance": out.provenance,
        }, f"Asking a human: {out.reason}.")
        reply = self.human(esc.content | {"escalation_id": esc.id}, self) or {}
        decision = reply.get("decision", "reject")
        action = Action(reply.get("action", "noop")) if decision == "approve" else Action.NOOP
        self.publish(MessageType.HUMAN_RESPONSE, "human", {"decision": decision, "action": action.value,
                                                           "escalation_id": esc.id},
                     f"Human {decision}d" + (f" {action.value}" if action != Action.NOOP else "")
                     + (f" ({reply['note']})" if reply.get("note") else "") + ".")
        if action in (Action.NOOP, Action.PROBE):
            self.hold_until = self.tick + HOLD_TICKS
            self.probes_used = 0
            return Action.NOOP
        verdict = ad.validate(action, self.state, human_approved=True)
        if not verdict.allowed:
            self.publish(MessageType.VETO, "validator", {"action": action.value}, f"Blocked even with approval: {verdict.reason}.")
            return Action.NOOP
        if self.decision_belief is None:
            self.decision_belief = belief
        self.human_approved = True
        return self._apply(action, "human", [esc.id], f"Human-approved {action.value}. Validator: {verdict.reason}.")


def _mean(beliefs: list[Belief]) -> Belief:
    if not beliefs:
        return uniform_belief()
    return {h: sum(b[h] for b in beliefs) / len(beliefs) for h in Hypothesis}
