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

- **Simulator** (`simulator/`, stand-in in `standins/sim.py`). Four services
  (gateway → auth, payments; payments → database), 30 ticks, fault at
  tick 5, seeded noise and 5% flaky readings.
- **Router and engine** (`backend/engine.py`). This is plain code. It detects the
  incident, runs the runbook, and switches from deterministic to probabilistic
  handling when no rule matches, two rules match at once, the validator blocks the
  rule's fix, or a fix did not help. It also verifies fixes and computes metrics.
- **Agents** (`agents/agent_base.py`, `agents/registry.json`). There are five core
  agents, plus a Network Analyst recruited on demand. Each agent sees only its own
  3 features (partial information) and has its own goal, encoded as action costs
  and an action threshold. Gateway and Database can veto.
- **Evidence and rationale** (`agents/evidence.py`). The LLM reads the agent's
  raw log lines and returns feature levels plus a plain-English reason. The levels
  are cross-checked against the measured numbers. **The LLM never produces
  probabilities.**
- **Voice** (`agents/voice.py`). The LLM writes what agents *say*: challenges, the
  aggregator's explanation, the briefing a human reads before approving, and the
  end-of-run summary. The code has already decided what they *do*. A
  faithfulness guard rejects any sentence that invents a number, cause or action,
  and the template text is used instead.
- **Beliefs.** Each agent's beliefs come from a Bayesian update over 4 hypotheses
  using likelihood tables `P(level | hypothesis)`. Mode B pools them with a
  log-opinion pool.
- **Mode B: central aggregator.** It pools beliefs, then applies an expected-cost
  decision rule (`intelligence/decision.py`). There are no fixed confidence
  thresholds. Each choice is priced in "ticks of pain": act on the best fix the
  validator allows, probe first (at most 2 probes), or ask a human. The cheapest
  choice wins. Acting wrongly costs a wasted hold period, plus extra harm if the
  action is risky (`block_traffic`, `failover_db`), plus still needing a human. A
  probe costs a tick but halves the chance of being wrong. A human costs a fixed
  delay. As a result, cheap fixes are taken at modest confidence and risky ones
  only at high confidence, and the validator always has the last word.
- **Mode C: peer negotiation** (`agents/negotiation.py`). Each round has four steps:
  1. Every agent proposes an action.
  2. Every agent challenges the most confident peer that disagrees, sharing its own
     strongest evidence and asking for theirs.
  3. Both agents update their beliefs.
  4. Everyone votes.
  If the whole team names one cause but the Database agent is below its 85% veto bar for a
  failover, it asks its agreeing peers for evidence first (block_traffic gets no such round).
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

- **Mode B:** asking a human is the cheapest choice under the expected-cost rule.
  That happens when the remaining risk of acting wrongly (especially with a risky
  action) costs more than a human's delay and probing no longer helps, or when the
  validator blocks every fix worth taking.
- **Mode C:** no proposal gets a two-thirds quorum without a veto within 4 rounds,
  or a risky action fails to get a unanimous vote.

If the human rejects, the system holds for 4 ticks, then deliberates again from
fresh data. Every escalation shows the options with their probabilities and risks.

## LLM usage

The LLM is only used when the console's **LLM** box (or `use_llm`) is on, and only
at decision points, never every tick:

- **Evidence:** one call per agent per deliberation, after the router hands over.
- **Voice:** challenges in Mode C, the aggregator's explanation in Mode B, the
  human briefing on escalation, and one summary at the end of a run.

Answers are cached on disk (`.cache/llm`), so repeated runs are free:
`scripts/warm_llm_cache.py` pre-runs the demo incidents. Real calls are throttled
(`LLM_MAX_RPM`, default 12 per minute, for free tiers), and a rate-limit error is
retried after the wait the provider asks for. With no key, or if a call fails, the
system runs deterministically with template text. The LLM never decides anything:
actions, beliefs, votes and escalations all come from code.
