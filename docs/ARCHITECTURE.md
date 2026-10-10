# Architecture overview (draft for the submission)

## Flow

```
FaultInjector → Simulator ──noisy telemetry──▶ Router
                                              ├─ clear known failure ─▶ Runbook ───────────────┐
                                              └─ unclear / fix failed ─▶ Agent team            │
                                                     │ beliefs, challenges, evidence, votes     │
                                                     ▼                                          ▼
                                               Bus (shared channel) ── agreed action ──▶ Safety validator ─▶ Simulator
                                                     │                    └ deadlock / risky ─▶ Human ─┘
                                                     └──▶ Action ledger ─▶ Console (websocket)
```

## Components

- **Simulator** (`simulator/`, stand-in in `standins/sim.py`). Five services
  (gateway → auth, payments; payments → database, cache), 30 ticks, fault at
  tick 5, seeded noise and 5% flaky readings.
- **Router and engine** (`backend/engine.py`). This is plain code. It detects the
  incident, runs the runbook, and switches from deterministic to probabilistic
  handling when no rule matches or a fix did not help (and optionally when rules
  conflict). It also verifies fixes and computes metrics.
- **Agents** (`agents/agent_base.py`, `agents/registry.json`). There are five core
  agents, plus a Network Analyst recruited on demand. Each agent sees only its own
  3 features (partial information) and has its own goal, encoded as action costs
  and an action threshold. Gateway and Database can veto.
- **Evidence and rationale** (`agents/evidence.py`). The LLM reads the agent's
  raw log lines and returns feature levels plus a plain-English reason. The levels
  are cross-checked against the measured numbers. **The LLM never produces
  probabilities.**
- **Beliefs.** Each agent's beliefs come from a Bayesian update over 4 hypotheses
  using likelihood tables `P(level | hypothesis)`. Mode B pools them with a
  log-opinion pool.
- **Mode B: central aggregator.** It pools beliefs, then applies one decision rule:
  act if the top hypothesis clears the threshold (stricter for risky actions) and
  the validator allows it; otherwise probe (at most 2); otherwise escalate.
- **Mode C: peer negotiation** (`agents/negotiation.py`). Each round has four steps:
  1. Every agent proposes an action.
  2. Every agent challenges the most confident peer that disagrees, sharing its own
     strongest evidence and asking for theirs.
  3. Both agents update their beliefs.
  4. Everyone votes.
  A proposal passes with a two-thirds quorum and no veto, and risky actions need a
  unanimous vote. If nothing passes within 4 rounds, the team escalates to a human.
  No component pools beliefs or chooses the outcome.
- **Recruitment** (`agents/recruitment.py`). The initial team is chosen by
  capability, with a stated reason for each agent. The Network Analyst is found in
  the registry by the capability `dependency_timeout_analysis` when the team's
  mean P(dependency_timeout) is at least 0.30, or when nobody is confident.
- **Safety validator.** It hard-blocks rule-breaking actions and flags risky ones.
  A human approval can override a risk flag.
- **Bus** (`agents/bus.py`). An in-memory publish/subscribe channel with a
  websocket forwarder. Its interface is small so it can be swapped for AGNTCY
  (A2A over SLIM).
- **Console** (`frontend/`). It shows:
  - a React Flow service graph with health colours;
  - the agent roster with live belief bars and arrows showing change;
  - a mode indicator with the reason for the last switch;
  - an action ledger, filterable by agent;
  - a provenance drawer that follows a decision back to the messages behind it;
  - the human approval panel;
  - a results tab.

## Stop / ask-a-human rule

The system escalates to a human when either of these is true:

- **Mode B:** after 2 probes, the top hypothesis is still below threshold (0.75 for
  safe actions, 0.9 for risky ones), or the validator blocks the action.
- **Mode C:** no proposal gets a two-thirds quorum without a veto within 4 rounds,
  or a risky action fails to get a unanimous vote.

If the human rejects, the system holds for 4 ticks, then deliberates again from
fresh data. Every escalation shows the options with their probabilities and risks.

## LLM usage

There is one call per agent per deliberation, made only after the router hands
over. Calls are cached on disk, so repeated runs are free. On S2 in Mode C that
is 5 calls the first time and 0 on a re-run. With no key set, the system runs
deterministically with template reasons.
