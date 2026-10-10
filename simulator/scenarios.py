"""Scenario definitions: S1, S2, S5 (from the plan).

A scenario says which fault is REALLY happening, and whether some readings are
deliberately misleading ("decoys").
"""

from __future__ import annotations

from dataclasses import dataclass, field

from shared.types import Hypothesis, ScenarioId


@dataclass(frozen=True)
class Decoy:
    """Misleading signals that look like a different fault.

    hypothesis: which fault the decoy imitates (its readings are borrowed).
    strength:   0..1, how strongly the decoy readings show up.
    features:   which readings are affected (None = all of that fault's readings).
    prob:       chance (per run/seed) that the decoy is present at all.
    """

    hypothesis: Hypothesis
    strength: float
    features: frozenset[str] | None = None
    prob: float = 1.0


@dataclass(frozen=True)
class ScenarioSpec:
    id: str
    name: str
    true_fault: Hypothesis
    description: str = ""
    decoys: tuple[Decoy, ...] = ()
    # Replace the peak reading of a feature for the true fault (e.g. S5 lag).
    peak_overrides: dict[str, float] = field(default_factory=dict)


SCENARIOS: dict[ScenarioId, ScenarioSpec] = {
    # S1: clear, known failure. The runbook should handle this well.
    ScenarioId.S1: ScenarioSpec(
        id="S1",
        name="Clear database fault",
        true_fault=Hypothesis.DB_FAULT,
        description="Database fault with clean, unambiguous symptoms.",
    ),
    # S2: a bad deploy that looks like an attack on about 40% of seeds.
    # The runbook rule "error spike + traffic anomaly -> block_traffic" misfires.
    ScenarioId.S2: ScenarioSpec(
        id="S2",
        name="Bad deploy that looks like an attack",
        true_fault=Hypothesis.BAD_DEPLOY,
        description="A faulty release; sometimes traffic/login readings look like an attack.",
        decoys=(
            Decoy(
                hypothesis=Hypothesis.ATTACK,
                strength=0.9,
                features=frozenset({"traffic_anomaly", "failed_logins"}),
                prob=0.4,
            ),
        ),
    ),
    # S5: evidence is split between attack and db_fault, and the only fix
    # (failover_db) is risky because replication lag is above the safe limit.
    ScenarioId.S5: ScenarioSpec(
        id="S5",
        name="Ambiguous, high-stakes",
        true_fault=Hypothesis.DB_FAULT,
        description=(
            "Database fault with attack-like decoy signals. Failover is the real fix "
            "but risks data consistency; blocking traffic locks out customers."
        ),
        decoys=(Decoy(hypothesis=Hypothesis.ATTACK, strength=0.6, prob=1.0),),
        peak_overrides={"replication_lag_s": 14.0},
    ),
}


def custom_scenario(fault: Hypothesis) -> ScenarioSpec:
    """A plain scenario for one fault, with no decoys (handy for tests and demos)."""
    return ScenarioSpec(
        id=f"custom_{fault.value}",
        name=f"Plain {fault.value}",
        true_fault=fault,
        description="Single fault, no decoys.",
    )
