# Integration notes: Person B → Person A

Written for Person A. It covers what Person B's code expects from yours, and
what changed in `shared/`.

## Shared types changes (agreed)

1. `Message.id: int = 0`. The bus sets it on publish. The console uses it for
   decision provenance: an `action`/`escalate` message lists the ids that led to it
   in `content["provenance"]`.
2. `ScenarioId.S3` for dependency_timeout, used to show the Network Analyst being
   recruited.

## What `backend/adapters.py` uses now

| Piece | Source |
|---|---|
| Simulator | `simulator.sim.Simulator` (Person A) |
| Feature levels | `simulator.faults.level_of` (Person A) |
| Runbook rules | `simulator.runbook.runbook_matches` (Person A) |
| Safety validator | `simulator.validator.validate` (Person A), hard block at 12 s lag |
| Belief update, pooling, entropy, Brier, act/probe/escalate rule | **stand-ins** in `standins/intelligence.py`, until A4–A6 land |

Set `GHOST_STANDINS=1` to force every stand-in, for example for a safe demo.

When A5/A6 land, the engine expects:

- `intelligence/beliefs.py` → `class BeliefEngine` with `update(agent_id, belief, levels)`.
  This one is picked up automatically.
- The pool, entropy, Brier, decision rule and escalation options are swapped in
  one line each in `backend/adapters.py`. Their signatures are in
  `standins/intelligence.py`.

The engine reads `sim.state` and the dict returned by `step()`
(`error_rate`, `latency_ms`, `customer_lockout`), and it calls
`step(action, approved=True)` after a human approves an action. For the
recruited Network Analyst, `observe()` raises `KeyError`, so the engine builds
that agent's observation from `upstream_timeouts` in the state.

## Remaining stand-in choices to revisit with A4–A6

- The likelihood tables are hand-set from the fault signatures, not estimated
  from runs (that is A4).
- Mode B's decision rule uses P ≥ 0.75 for safe actions and P ≥ 0.9 for risky
  ones, with at most 2 probes before escalating. Mode C needs a unanimous vote
  for risky actions.
- The evaluation uses a scripted "oracle" human, who approves the correct fix
  when it is offered.
- Mode D applies the first matching runbook rule even when rules conflict, so
  the S2 misfire is visible. Set `escalate_on_conflict=True` to change that.

## Numbers on Person A's simulator, runbook and validator (20 seeds, `eval/results/compare.json`)

| | A runbook | B aggregator | C negotiation | D hybrid→C |
|---|---|---|---|---|
| S1 correct | 100% | 100% | 100% | 100% |
| S2 correct | 75% | 100% | 100% | 75% |
| S3 correct | 100% | 100% | 100% | 100% |
| S5 correct / asked human | 0% / 0% (never recovers) | 100% / 100% | 100% / 100% | 70% / 100% |

Ablation (`eval/results/compare_ablate_database.json`): removing the Database
agent's evidence makes S1 need a human 90–95% of the time (versus 0–10%), and
drops S5 correct diagnosis from 100% to 0–15%. Removing the Deployment agent
changes little, because the others infer bad_deploy by elimination. That is
worth a sentence in the lessons learned.
