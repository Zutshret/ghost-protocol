"""Watch the simulator run. Prints one line per tick.

Run:  uv run python scripts/demo_sim.py

Columns: tick, severity (0 healthy .. 1 worst), true error rate, true latency,
availability, whether we recovered, and what action was taken.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))  # so "shared" and "simulator" import

from shared.types import Action, ScenarioId  # noqa: E402
from simulator.sim import Simulator  # noqa: E402


def show(title: str, scenario: ScenarioId, seed: int, actions: dict[int, Action], **kw) -> None:
    sim = Simulator()
    sim.reset(scenario, seed)
    print(f"\n=== {title} (scenario {scenario.value}, seed {seed}) ===")
    print(f"True fault (hidden from agents): {sim.true_fault.value}")
    print(f"{'tick':>4} {'sev':>5} {'err%':>6} {'lat_ms':>7} {'avail':>6}  action / note")
    while sim.tick < Simulator.N_TICKS:
        act = actions.get(sim.tick, Action.NOOP)
        sim.step(act, **kw)
        t = sim.truth
        note = "" if act == Action.NOOP else act.value
        if sim.is_recovered() and sim.recovery_tick == sim.tick:
            note += "  <-- RECOVERED"
        print(
            f"{sim.tick:>4} {t['severity']:>5.2f} {t['edge_error_rate_true'] * 100:>6.1f} "
            f"{t['latency_ms_true']:>7.0f} {t['availability']:>6.2f}  {note}"
        )
        if sim.finished:
            break
    s = sim.summary()
    print(
        f"Result: recovered={s['recovered']}, recovery_time={s['recovery_time']}, "
        f"availability={s['availability']:.3f}, unnecessary_actions={s['unnecessary_actions']}, "
        f"correct_diagnosis={s['correct_diagnosis']}"
    )


def show_agent_view(scenario: ScenarioId, seed: int, until_tick: int) -> None:
    sim = Simulator()
    sim.reset(scenario, seed)
    while sim.tick < until_tick:
        sim.step()
    print(f"\n=== What each agent sees at tick {sim.tick} (scenario {scenario.value}, seed {seed}) ===")
    for agent in ["gateway", "payments", "database", "security", "deployment"]:
        obs = sim.observe(agent)
        print(f"[{agent}]")
        for line, level in zip(obs.logs, obs.levels.values()):
            print(f"   {line:<55} -> {level.value}")


if __name__ == "__main__":
    show("1. Do nothing: the fault just gets worse", ScenarioId.S1, 1, {})
    show("2. Correct fix at tick 7", ScenarioId.S1, 1, {7: Action.FAILOVER_DB})
    show(
        "3. Wrong action first (block traffic), then the right fix",
        ScenarioId.S2,
        1,
        {7: Action.BLOCK_TRAFFIC, 13: Action.ROLLBACK_DEPLOY},
    )
    show_agent_view(ScenarioId.S1, 1, 10)
