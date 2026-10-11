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
| Belief engine, `log_pool`, `entropy`, `brier`, `failed_action_update` | `intelligence.beliefs` (Person A, A4/A5) |
| `decide` (act/probe/escalate), `escalation_options` | `intelligence.decision` (Person A, A6) |

`standins/` is kept only as a fallback: set `GHOST_STANDINS=1` to force every
stand-in, for example for a safe demo. `tests/test_person_b.py` uses it so those
tests don't depend on the tuning in `likelihoods.json`.

The engine reads `sim.state` and the dict returned by `step()`
(`error_rate`, `latency_ms`, `customer_lockout`), and it calls
`step(action, approved=True)` after a human approves an action. For the
recruited Network Analyst, `observe()` raises `KeyError`, so the engine builds
that agent's observation from `upstream_timeouts` in the state.

## Choices on Person B's side

- Mode C needs a unanimous vote for risky actions (2/3 otherwise). Gateway and
  Database veto block_traffic / failover_db unless they are at least 85% sure.
- The evaluation uses a scripted "oracle" human, who approves the correct fix
  when it is offered.
- Mode D hands over to the agents when two runbook rules match (`escalate_on_conflict`,
  on by default). With it off, Mode D applies the first matching rule and reproduces the runbook's
  S2 misfire; `eval/results/REPORT.md` section 6 reports both.

## Numbers on the full real stack (20 seeds, `eval/results/compare.json`)

| | A runbook | B aggregator | C negotiation | D hybrid→C |
|---|---|---|---|---|
| S1 correct | 100% | 100% | 100% | 100% |
| S2 correct | 75% | 100% | 100% | 75% |
| S3 correct | 100% | 100% | 100% | 100% |
| S5 correct / asked human | 0% / 0% (never recovers) | 95% / 100% | 95% / 100% | 85% / 100% |

Ablation (`eval/results/compare_ablate_database.json`): removing the Database
agent's evidence makes Mode C ask a human on S1 every time (versus 5%), because
nobody can vouch for the failover, and drops S5 correct diagnosis from 95% to 0–5%. Removing the Deployment agent
changes little, because the others infer bad_deploy by elimination. That is
worth a sentence in the lessons learned.
