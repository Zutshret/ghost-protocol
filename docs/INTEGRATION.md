# Integration notes: Person B → Person A

Written for Person A. It covers what Person B's code expects from yours, and
what changed in `shared/`.

## Shared types changes (please confirm)

1. `Message.id: int = 0`. The bus sets it on publish. The console uses it for
   decision provenance: an `action`/`escalate` message lists the ids that led to it
   in `content["provenance"]`.
2. `ScenarioId.S3` for dependency_timeout. It is used to show the Network Analyst
   being recruited (B7). If you'd rather not support it, the console still works
   and only that demo is lost.

Both are additive, so no existing code breaks.

## What gets picked up automatically

`backend/adapters.py` uses your modules as soon as they exist, and the stand-ins
in `standins/` until then. Set `GHOST_STANDINS=1` to force the stand-ins.

| Expected | Used for |
|---|---|
| `simulator/sim.py` → `class Simulator` with `reset(scenario, seed)`, `step(action) -> dict`, `observe(agent_id) -> Observation`, `is_recovered()` | everything |
| `Simulator.true_fault` (a `Hypothesis`) | metrics, scripted human in eval |
| `Simulator.state` (latest raw dict, optional) and `Simulator.tick` | telemetry before the first step |
| `step()` dict keys: the 15 features + `error_rate`, `latency_ms`, `customer_lockout` | metrics, service health colours |
| `intelligence/beliefs.py` → `class BeliefEngine` with `update(agent_id, belief, levels)` | every agent's belief |

The engine calls `observe("network_analyst")` for the recruited agent. If your
simulator raises `KeyError` or `ValueError` there, the engine builds that agent's
observation from the raw state instead. Its features are
`downstream_p99_ms`, `conn_pool_saturation` and `upstream_timeouts`; only the
last one exists without the stand-in.

## Still stand-ins (swap one line each in `backend/adapters.py`)

`log_pool`, `entropy`, `brier`, `failed_action_update`, `runbook_matches`,
`validate`, `decide` (act/probe/escalate), `escalation_options`, `level_of`.
Their signatures are in `standins/intelligence.py`. If yours differ, adjust the
adapter rather than the callers.

## Decisions made in the stand-ins that you may want to revisit

- **Validator vs S1.** The cheat sheet says the S1 runbook fixes the fault with
  `failover_db` while replication lag is high, and also that the validator blocks
  failover while lag is high. The stand-in hard-blocks only above 20 s of lag and
  marks failover as *risky* otherwise. Mode B needs P ≥ 0.9 for risky actions
  (0.75 for safe ones); Mode C needs a unanimous vote for risky actions.
- **S5 ground truth** is `db_fault` with an attack-like traffic surge. The
  evaluation uses a scripted "oracle" human who approves the correct fix if it
  is among the offered options.
- **Probe** gives one tick of cleaner readings (less noise, no flaky values),
  not an extra hidden feature.
- **Detection** needs 3 bad ticks in a row, so flaky readings don't open an
  incident. A fix counts as "failed" if, after 4 ticks, the badness is not
  below half its peak.
- **Mode D** applies the first matching runbook rule even when rules conflict, so
  the S2 decoy misfire is visible. Set `escalate_on_conflict=True` to hand
  conflicts straight to the agents.

## Current stand-in numbers (30 seeds, `eval/results/compare.json`)

| | A runbook | B aggregator | C negotiation | D hybrid→C |
|---|---|---|---|---|
| S1 correct | 100% | 100% | 100% | 100% |
| S2 correct | 60% | 100% | 100% | 60% |
| S5 correct / asked human | 3% / 0% | 83% / 97% | 97% / 97% | 20% / 87% |

The ablation result is in `eval/results/compare_ablate_database.json`. Removing
the Database agent's evidence drops S5 correct diagnosis to 0%, and S1 in Mode C
then needs a human every time. Removing the Deployment agent changes little,
because the others still infer bad_deploy by elimination. That is worth a sentence
in the lessons learned.
