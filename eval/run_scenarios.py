"""Run a mode across scenarios and many seeds, then summarize (task A2).

Today this runs Mode A (the deterministic runbook baseline) directly against
the simulator. Modes B, C and D need the agent team, so they run through
Person B's engine (eval/compare_modes.py, once their branch is merged).

Examples:
    uv run python eval/run_scenarios.py --mode A --seeds 50
    uv run python eval/run_scenarios.py --mode A --scenarios S1 S2 --seeds 100 --out eval/results/a.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "shared" and "simulator" import

import numpy as np  # noqa: E402

from shared.types import Action, Mode, RunMetrics, ScenarioId  # noqa: E402
from simulator.runbook import Runbook  # noqa: E402
from simulator.sim import Simulator  # noqa: E402

DEFAULT_SCENARIOS = [ScenarioId.S1, ScenarioId.S2, ScenarioId.S5]


def global_view(sim: Simulator):
    """What the runbook sees: every dashboard (all agents' readings combined)."""
    readings: dict[str, float] = {}
    levels = {}
    for agent_id in ["gateway", "payments", "database", "security", "deployment"]:
        obs = sim.observe(agent_id)
        readings.update(obs.values)
        levels.update(obs.levels)
    return readings, levels


def run_mode_a(scenario: ScenarioId, seed: int, trace: list[dict] | None = None) -> dict:
    """One incident handled by the runbook alone. Returns one row of results."""
    sim = Simulator()
    sim.reset(scenario, seed)
    runbook = Runbook()
    while not sim.finished:
        readings, levels = global_view(sim)
        action = runbook.decide(sim.tick, readings, levels)
        if trace is not None:
            trace.append({"tick": sim.tick, "action": action.value, "note": runbook.last_note})
        sim.step(action)

    s = sim.summary()
    metrics = RunMetrics(
        scenario=scenario,
        mode=Mode.A,
        seed=seed,
        true_fault=s["true_fault"],
        recovery_time=s["recovery_time"],
        availability=round(s["availability"], 4),
        unnecessary_actions=s["unnecessary_actions"],
        correct_diagnosis=s["correct_diagnosis"],
        escalated_to_human=False,
        brier_score=None,  # the runbook has no probabilities
        llm_calls=0,
    )
    row = metrics.model_dump(mode="json")
    row["recovered"] = s["recovered"]
    row["consistency_violations"] = s["consistency_violations"]
    row["blocked_by_validator"] = len(runbook.blocked_log)
    return row


def summarize(rows: list[dict]) -> dict:
    """Averages (with 95% ranges) per scenario."""
    out: dict[str, dict] = {}
    for scenario in sorted({r["scenario"] for r in rows}):
        sub = [r for r in rows if r["scenario"] == scenario]
        n = len(sub)

        def mean_ci(key: str) -> dict:
            vals = np.array([float(r[key]) for r in sub])
            half = 1.96 * vals.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0
            return {"mean": round(float(vals.mean()), 4), "ci95": round(float(half), 4)}

        out[scenario] = {
            "runs": n,
            "recovered_rate": round(sum(r["recovered"] for r in sub) / n, 4),
            "correct_diagnosis_rate": round(sum(r["correct_diagnosis"] for r in sub) / n, 4),
            "consistency_violation_rate": round(sum(r["consistency_violations"] > 0 for r in sub) / n, 4),
            "recovery_time": mean_ci("recovery_time"),
            "availability": mean_ci("availability"),
            "unnecessary_actions": mean_ci("unnecessary_actions"),
        }
    return out


def print_table(mode: str, summary: dict) -> None:
    print(f"\nMode {mode}: results per scenario")
    header = f"{'scenario':<9}{'runs':>5}{'recovered':>11}{'correct 1st':>13}{'recovery (ticks)':>20}{'availability':>15}{'wrong actions':>15}{'consistency risk':>18}"
    print(header)
    print("-" * len(header))
    for sc, s in summary.items():
        rt, av, un = s["recovery_time"], s["availability"], s["unnecessary_actions"]
        print(
            f"{sc:<9}{s['runs']:>5}{s['recovered_rate']:>11.0%}{s['correct_diagnosis_rate']:>13.0%}"
            f"{rt['mean']:>13.1f} +/-{rt['ci95']:<4.1f}{av['mean']:>10.3f} +/-{av['ci95']:<.3f}"
            f"{un['mean']:>9.2f}{s['consistency_violation_rate']:>14.0%}"
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--mode", default="A", help="A (runbook). B, C, D need Person B's engine.")
    parser.add_argument("--scenarios", nargs="+", default=[s.value for s in DEFAULT_SCENARIOS])
    parser.add_argument("--seeds", type=int, default=50, help="how many seeds per scenario")
    parser.add_argument("--out", default=None, help="where to save JSON (default eval/results/baseline_<mode>.json)")
    args = parser.parse_args()

    mode = args.mode.upper()
    if mode != "A":
        print(
            f"Mode {mode} uses the agent team, which lives in Person B's engine.\n"
            "Run it with eval/compare_modes.py after their branch is merged."
        )
        return 2

    scenarios = [ScenarioId(s) for s in args.scenarios]
    rows = [run_mode_a(sc, seed) for sc in scenarios for seed in range(args.seeds)]
    summary = summarize(rows)
    print_table(mode, summary)

    out = Path(args.out) if args.out else Path(__file__).parent / "results" / f"baseline_{mode}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"mode": mode, "seeds": args.seeds, "summary": summary, "rows": rows}, indent=2))
    print(f"\nSaved {len(rows)} runs to {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
