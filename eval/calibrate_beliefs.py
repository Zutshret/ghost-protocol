"""Check how trustworthy the belief engine's confidence is (A5 sanity check, feeds A8).

For each scenario and many fresh seeds (2000+, never used for training), pool every
agent's clues at the moments agents would reason (ticks 7-12) and ask:
- how often is the top guess right?
- when it says "90% sure", is it right ~90% of the time?  (calibration)
- Brier score: lower is better.

Run:  uv run python eval/calibrate_beliefs.py
      uv run python eval/calibrate_beliefs.py --temperatures 0.25 0.5 1.0
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import numpy as np  # noqa: E402

from intelligence.beliefs import BeliefEngine, brier, entropy  # noqa: E402
from shared.types import AGENT_IDS, Action, ScenarioId, uniform_belief  # noqa: E402
from simulator.sim import Simulator  # noqa: E402

TEST_SEEDS = range(2000, 2060)
TICKS = range(7, 13)


def evaluate(temperature: float, scenarios: list[ScenarioId]) -> dict:
    engine = BeliefEngine(temperature=temperature)
    sim = Simulator()
    out = {}
    for sc in scenarios:
        confs, hits, briers, ents = [], [], [], []
        for seed in TEST_SEEDS:
            sim.reset(sc, seed)
            while sim.tick <= max(TICKS):
                if sim.tick in TICKS:
                    levels = {}
                    for a in AGENT_IDS:
                        levels.update(sim.observe(a).levels)
                    b = engine.update("all", uniform_belief(), levels)
                    top = max(b, key=b.get)
                    confs.append(b[top])
                    hits.append(top == sim.true_fault)
                    briers.append(brier(b, sim.true_fault))
                    ents.append(entropy(b))
                sim.step(Action.NOOP)
        out[sc.value] = {
            "accuracy": float(np.mean(hits)),
            "avg_confidence": float(np.mean(confs)),
            "brier": float(np.mean(briers)),
            "entropy_bits": float(np.mean(ents)),
        }
    return out


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--temperatures", nargs="+", type=float, default=[1.0])
    p.add_argument("--scenarios", nargs="+", default=["S1", "S2", "S3", "S5"])
    args = p.parse_args()
    scenarios = [ScenarioId(s) for s in args.scenarios]
    print(f"{'temp':>5} {'scenario':<9}{'accuracy':>10}{'avg conf':>10}{'brier':>8}{'entropy':>9}")
    for t in args.temperatures:
        for sc, m in evaluate(t, scenarios).items():
            print(f"{t:>5} {sc:<9}{m['accuracy']:>10.0%}{m['avg_confidence']:>10.0%}{m['brier']:>8.3f}{m['entropy_bits']:>9.2f}")


if __name__ == "__main__":
    main()
