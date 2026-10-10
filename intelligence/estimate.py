"""A4: learn the likelihood tables from simulator runs.

The idea, in plain words
------------------------
The belief engine needs to answer: "if the real cause were X, how often would
this feature read LOW / MEDIUM / HIGH?" Instead of guessing, we ask the
simulator. For each possible cause we run the incident many times (plain
scenario, no decoys), watch every feature in the first ticks after the incident
opens, and count how often each level showed up.

    P(level | cause) = (count + 1) / (total + 3)      <- the "+1" is smoothing,
                                                         so nothing is ever 0%.

The counts are saved to `intelligence/likelihoods.json` so results are
repeatable. Training seeds (1000-1199) never overlap with evaluation seeds.

Run:  uv run python -m intelligence.estimate
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from shared.types import AGENT_IDS, Action, Hypothesis, Level  # noqa: E402
from simulator.scenarios import custom_scenario  # noqa: E402
from simulator.sim import Simulator  # noqa: E402

TABLE_PATH = Path(__file__).with_name("likelihoods.json")
LEVELS = (Level.LOW, Level.MEDIUM, Level.HIGH)

TRAIN_SEEDS = range(1000, 1200)  # 200 runs per cause
# Agents reason while an incident is open: from 2 ticks after the fault starts
# until the fault is at full strength.
WINDOW = range(Simulator.FAULT_START + 2, Simulator.FAULT_START + 8)  # ticks 7..12
SMOOTHING = 1.0  # add-one smoothing


def collect_counts(seeds=TRAIN_SEEDS, window=WINDOW) -> dict[str, dict[str, dict[str, int]]]:
    """counts[cause][feature][level] over all runs and ticks in the window."""
    counts: dict[str, dict[str, dict[str, int]]] = {}
    sim = Simulator()
    for h in Hypothesis:
        per_feature: dict[str, dict[str, int]] = {}
        for seed in seeds:
            sim.reset(custom_scenario(h), seed)
            while sim.tick <= max(window):
                if sim.tick in window:
                    for agent_id in AGENT_IDS:
                        for feature, level in sim.observe(agent_id).levels.items():
                            cell = per_feature.setdefault(feature, {lv.value: 0 for lv in LEVELS})
                            cell[Level(level).value] += 1
                sim.step(Action.NOOP)
        counts[h.value] = per_feature
    return counts


def to_probabilities(counts: dict[str, dict[str, dict[str, int]]], smoothing: float = SMOOTHING) -> dict:
    table: dict[str, dict[str, dict[str, float]]] = {}
    for h, features in counts.items():
        table[h] = {}
        for feature, cell in features.items():
            total = sum(cell.values()) + smoothing * len(LEVELS)
            table[h][feature] = {lv.value: (cell[lv.value] + smoothing) / total for lv in LEVELS}
    return table


def build_table() -> dict:
    counts = collect_counts()
    return {
        "meta": {
            "how": "counted from simulator runs (plain scenarios, no decoys), add-one smoothing",
            "train_seeds": [TRAIN_SEEDS.start, TRAIN_SEEDS.stop - 1],
            "window_ticks": [WINDOW.start, WINDOW.stop - 1],
            "runs_per_cause": len(TRAIN_SEEDS),
        },
        "counts": counts,
        "likelihood": to_probabilities(counts),
    }


def save_table(path: Path = TABLE_PATH) -> dict:
    table = build_table()
    path.write_text(json.dumps(table, indent=1))
    return table


def main() -> None:
    table = save_table()
    print(f"Saved {TABLE_PATH}")
    print(f"({table['meta']['runs_per_cause']} runs per cause, ticks {table['meta']['window_ticks']})\n")
    like = table["likelihood"]
    features = sorted(next(iter(like.values())))
    causes = [h.value for h in Hypothesis]
    print("P(HIGH | cause)   <- how often each feature reads HIGH under each cause")
    print(f"{'feature':<22}" + "".join(f"{c:>20}" for c in causes))
    for f in features:
        print(f"{f:<22}" + "".join(f"{like[c][f]['high']:>20.2f}" for c in causes))


if __name__ == "__main__":
    main()
