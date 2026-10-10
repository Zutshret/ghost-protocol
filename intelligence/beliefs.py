"""A5: the belief engine (Bayes' rule) plus the belief math helpers.

The idea, in plain words
------------------------
A *belief* is a list of probabilities, one per possible cause (they add up to 1).
Start with no opinion (25% each). Every clue nudges the numbers:

    new belief for cause X  ~  old belief for cause X  x  P(this clue | cause X)

then rescale so they add up to 1 again. A clue that is common under X but rare
under the others pushes X up. That is all Bayes' rule is.

Example: "replication lag is HIGH". The learned table says that is HIGH ~96% of
the time if the cause is db_fault, but only ~2% under the others. So db_fault
jumps from 25% to ~70% from that single clue, and to ~99% once slow queries and
lock waits are also HIGH.

Other helpers in this file:
- `log_pool`           combine several agents' beliefs (a weighted "geometric vote").
- `failed_action_update`  "we tried X and it did not help" lowers whatever X fixes.
- `entropy`            how unsure a belief is (0 = certain, 2 bits = no idea).
- `brier`              how wrong a belief was once the truth is known (lower is better).

Same names and signatures as the stand-ins in Person B's `standins/intelligence.py`.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

from shared.types import CORRECT_FIX, Action, Belief, Hypothesis, Level, uniform_belief

TABLE_PATH = Path(__file__).with_name("likelihoods.json")

# How strongly one clue counts. 1.0 = textbook Bayes. Below 1 means "don't fully
# trust the numbers" (clues from one incident are correlated, so they are not
# fully independent). Chosen with eval/calibrate_beliefs.py: at 1.0 the engine
# claims 93% confidence on the ambiguous scenario S5 while being right 80% of
# the time; at 0.5 it claims 84% (best Brier score), so its confidence is honest.
DEFAULT_TEMPERATURE = 0.5

_MIN_P = 1e-9


def load_table(path: Path = TABLE_PATH) -> dict[str, dict[str, dict[str, float]]]:
    """Likelihood tables; built from the simulator on first use if the file is missing."""
    if not path.exists():
        from intelligence.estimate import save_table

        return save_table(path)["likelihood"]
    return json.loads(path.read_text())["likelihood"]


def normalize(weights: dict) -> Belief:
    total = sum(weights.values())
    if total <= 0:
        return uniform_belief()
    return {Hypothesis(h): v / total for h, v in weights.items()}


class BeliefEngine:
    """Turns clues (feature levels) into updated beliefs. Implements `BeliefEngineAPI`."""

    def __init__(self, table: dict | None = None, temperature: float = DEFAULT_TEMPERATURE):
        self.table = table if table is not None else load_table()
        self.temperature = temperature

    # ---- the core update -------------------------------------------------
    def likelihood(self, feature: str, level: Level, hypothesis: Hypothesis) -> float:
        """P(this feature reads this level | this is the cause). Unknown feature -> 1 (no information)."""
        cell = self.table.get(hypothesis.value, {}).get(feature)
        if cell is None:
            return 1.0
        return cell[Level(level).value]

    def update(self, agent_id: str, belief: Belief, levels: dict[str, Level]) -> Belief:
        """Fold in the clues in `levels` and return the new belief.

        `agent_id` says who reported the clues (kept for logging). Features this
        engine has no table for (for example a freshly recruited specialist's)
        are skipped instead of crashing.
        """
        log_post = {h: math.log(max(belief.get(h, 0.0), _MIN_P)) for h in Hypothesis}
        for feature, level in levels.items():
            for h in Hypothesis:
                log_post[h] += self.temperature * math.log(max(self.likelihood(feature, level, h), _MIN_P))
        peak = max(log_post.values())
        return normalize({h: math.exp(v - peak) for h, v in log_post.items()})

    # ---- explanations (for the console and the write-up) ------------------
    def explain(self, levels: dict[str, Level]) -> list[dict]:
        """For each clue, how many 'bits' of support it gives each cause (vs. the average).

        Positive = pushes toward that cause. Sorted by how decisive the clue is.
        """
        rows = []
        for feature, level in levels.items():
            logs = {h: math.log2(max(self.likelihood(feature, level, h), _MIN_P)) for h in Hypothesis}
            mean = sum(logs.values()) / len(logs)
            support = {h.value: round(v - mean, 2) for h, v in logs.items()}
            rows.append({"feature": feature, "level": Level(level).value, "support_bits": support,
                         "strength": round(max(support.values()) - min(support.values()), 2)})
        return sorted(rows, key=lambda r: -r["strength"])


# --------------------------------------------------------------------------
# Belief math helpers
# --------------------------------------------------------------------------
def failed_action_update(belief: Belief, action: Action, strength: float = 0.15) -> Belief:
    """'We tried this action and it did not help' is evidence against what it fixes."""
    post = {h: belief.get(h, 0.0) for h in Hypothesis}
    for h, fix in CORRECT_FIX.items():
        if fix == action:
            post[h] *= strength
    return normalize(post)


def log_pool(beliefs: list[Belief], weights: list[float] | None = None) -> Belief:
    """Combine several beliefs by multiplying (adding in log space), optionally weighted.

    If agents hold independent evidence this equals one big Bayes update. A confident
    "no" from any agent is hard to overrule, which is what we want for safety.
    """
    if not beliefs:
        return uniform_belief()
    weights = weights or [1.0] * len(beliefs)
    logp = {h: 0.0 for h in Hypothesis}
    for b, w in zip(beliefs, weights):
        for h in Hypothesis:
            logp[h] += w * math.log(max(b.get(h, 0.0), _MIN_P))
    peak = max(logp.values())
    return normalize({h: math.exp(v - peak) for h, v in logp.items()})


def entropy(belief: Belief) -> float:
    """Uncertainty in bits: 0 = certain, log2(4) = 2 = no idea."""
    return -sum(p * math.log2(p) for p in belief.values() if p > 0)


def brier(belief: Belief, truth: Hypothesis) -> float:
    """Squared error against the truth: 0 = perfect, 2 = confidently wrong."""
    return sum((belief.get(h, 0.0) - (1.0 if h == truth else 0.0)) ** 2 for h in Hypothesis)


__all__ = [
    "BeliefEngine", "failed_action_update", "log_pool", "entropy", "brier", "load_table", "normalize",
]
