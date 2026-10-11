"""A8: the official evaluation.

Runs everything the write-up needs and saves it under eval/results/:
  official.json               modes A-D x scenarios (shows up in the console's Results tab)
  official_ablation.json      what happens when one agent's evidence is removed
  official_decision_rule.json expected-cost rule vs fixed thresholds vs different human costs
  official_mode_d.json        Mode D with and without the 'two runbook rules match' hand-off
  REPORT.md                   all tables in readable form (paste into the write-up)

Seeds: evaluation uses seeds 0..N-1. The likelihood tables were learned on seeds
1000-1199 and calibration checks use 2000+, so nothing here was tuned on test seeds.

    uv run python eval/evaluate.py                # 100 seeds per cell (about a minute)
    uv run python eval/evaluate.py --seeds 30     # quick check
"""

from __future__ import annotations

import argparse
import json
import math
import statistics
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend import adapters  # noqa: E402
from backend.engine import IncidentEngine  # noqa: E402
from eval.calibrate_beliefs import evaluate as engine_calibration  # noqa: E402
from intelligence.decision import CostModel, decide as expected_cost_decide  # noqa: E402
from shared.types import AGENT_IDS, Mode, ScenarioId  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"
SCENARIOS = ["S1", "S2", "S3", "S5"]
MODES = ["A", "B", "C", "D"]
MODE_NAME = {"A": "Runbook", "B": "Agents + aggregator", "C": "Peer negotiation", "D": "Hybrid"}
SCENARIO_NAME = {"S1": "clear DB fault", "S2": "deploy that looks like an attack", "S3": "dependency timeout", "S5": "ambiguous, high stakes"}
METRICS = ["correct_diagnosis", "recovery_time", "availability", "unnecessary_actions",
           "escalated_to_human", "unsafe_action", "brier_score"]
FIRST_TEST_SEED = 0


# --------------------------------------------------------------------------
# Running
# --------------------------------------------------------------------------
def run_one(scenario: str, mode: str, seed: int, ablate: str | None = None, **engine_kwargs) -> dict:
    eng = IncidentEngine(scenario, mode, seed, ablate=ablate, agents_mode_for_d=Mode.C, **engine_kwargs)
    m = eng.run()
    row = m.model_dump(mode="json")
    row["unsafe_action"] = eng.sim.summary()["consistency_violations"] > 0  # failover that risked data
    row["ablated"] = ablate
    return row


def run_grid(seeds: range, scenarios=SCENARIOS, modes=MODES, ablate: str | None = None) -> list[dict]:
    return [run_one(sc, mode, seed, ablate) for sc in scenarios for mode in modes for seed in seeds]


# --------------------------------------------------------------------------
# Statistics
# --------------------------------------------------------------------------
def wilson(successes: int, n: int, z: float = 1.96) -> tuple[float, float, float]:
    """Proportion with a 95% Wilson interval (stays inside 0..100%, unlike the normal one)."""
    p = successes / n
    centre = (p + z * z / (2 * n)) / (1 + z * z / n)
    half = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / (1 + z * z / n)
    return p, max(0.0, centre - half), min(1.0, centre + half)


def mean_ci(vals: list[float]) -> tuple[float, float, float]:
    """Mean and 95% confidence interval. Yes/no metrics use the Wilson interval."""
    if vals and all(v in (0.0, 1.0) for v in vals):
        return wilson(int(sum(vals)), len(vals))
    m = statistics.fmean(vals)
    if len(vals) < 2:
        return m, m, m
    half = 1.96 * statistics.stdev(vals) / math.sqrt(len(vals))
    return m, m - half, m + half


def summarize(rows: list[dict], keys: tuple[str, ...] = ("scenario", "mode")) -> list[dict]:
    """One summary row per (scenario, mode): n and mean/lo/hi for every metric."""
    cells: dict[tuple, list[dict]] = {}
    for r in rows:
        cells.setdefault(tuple(r[k] for k in keys), []).append(r)
    out = []
    for key, rs in cells.items():
        row = dict(zip(keys, key))
        row["n"] = len(rs)
        for k in METRICS:
            vals = [float(r[k]) for r in rs if r.get(k) is not None]
            if vals:
                row[f"{k}_mean"], row[f"{k}_lo"], row[f"{k}_hi"] = (round(x, 4) for x in mean_ci(vals))
        out.append(row)
    return out


def paired_difference(rows: list[dict], scenario: str, mode: str, metric: str, baseline: str = "A") -> tuple[float, float, float]:
    """Same seeds, mode minus baseline: mean difference and 95% CI."""
    by_seed = {r["seed"]: float(r[metric]) for r in rows if r["scenario"] == scenario and r["mode"] == mode}
    base = {r["seed"]: float(r[metric]) for r in rows if r["scenario"] == scenario and r["mode"] == baseline}
    return mean_ci([by_seed[s] - base[s] for s in by_seed if s in base])


# --------------------------------------------------------------------------
# Experiments
# --------------------------------------------------------------------------
def main_comparison(seeds: range) -> tuple[list[dict], list[dict]]:
    rows = run_grid(seeds)
    return rows, summarize(rows)


def ablation(seeds: range) -> list[dict]:
    """Remove one agent's evidence at a time (modes B and C)."""
    rows = [dict(r, ablated="none") for r in run_grid(seeds, modes=["B", "C"])]
    for agent in AGENT_IDS:
        rows += [dict(r, ablated=agent) for r in run_grid(seeds, modes=["B", "C"], ablate=agent)]
    return summarize(rows, keys=("ablated", "scenario", "mode"))


D_VARIANTS = {
    "conflict hand-off (default)": True,
    "naive: first matching rule wins": False,
}


def mode_d_variants(seeds: range) -> list[dict]:
    """Mode D with and without the router's 'two runbook rules match' hand-off.

    The default (hand off) was chosen after seeing that the naive setting just reproduces the
    runbook's S2 misfire, so both are reported."""
    rows: list[dict] = []
    for name, flag in D_VARIANTS.items():
        rows += [dict(run_one(sc, "D", seed, escalate_on_conflict=flag), variant=name)
                 for sc in SCENARIOS for seed in seeds]
    return summarize(rows, keys=("variant", "scenario", "mode"))


def decision_rule_variants(seeds: range) -> list[dict]:
    """Mode B with different decision rules plugged into the same engine."""
    from standins import intelligence as standin  # Person B's fixed-threshold rule

    original = (adapters.decide, adapters.escalation_options)
    variants = {
        "expected-cost (default)": (expected_cost_decide, original[1]),
        "fixed thresholds (75% / 90%)": (standin.decide, standin.escalation_options),
        "expected-cost, human is cheap (1)": (lambda p, s, n: expected_cost_decide(p, s, n, CostModel(human_cost=1.0)), original[1]),
        "expected-cost, human is costly (8)": (lambda p, s, n: expected_cost_decide(p, s, n, CostModel(human_cost=8.0)), original[1]),
    }
    rows: list[dict] = []
    try:
        for name, (decide_fn, options_fn) in variants.items():
            adapters.decide, adapters.escalation_options = decide_fn, options_fn
            rows += [dict(r, rule=name) for r in run_grid(seeds, modes=["B"])]
    finally:
        adapters.decide, adapters.escalation_options = original
    return summarize(rows, keys=("rule", "scenario", "mode"))


# --------------------------------------------------------------------------
# Report
# --------------------------------------------------------------------------
def fmt(row: dict, key: str, pct: bool = False, digits: int = 2) -> str:
    if f"{key}_mean" not in row:
        return "n/a"
    m, lo, hi = row[f"{key}_mean"], row[f"{key}_lo"], row[f"{key}_hi"]
    if pct:
        return f"{m:.0%} ({lo:.0%} to {hi:.0%})"
    return f"{m:.{digits}f} ({lo:.{digits}f} to {hi:.{digits}f})"


def signed(t: tuple[float, float, float], pct: bool = False, digits: int = 2) -> str:
    m, lo, hi = t
    if pct:
        return f"{m * 100:+.0f} pts ({lo * 100:+.0f} to {hi * 100:+.0f})"
    return f"{m:+.{digits}f} ({lo:+.{digits}f} to {hi:+.{digits}f})"


def table(headers: list[str], body: list[list[str]]) -> str:
    lines = ["| " + " | ".join(headers) + " |", "|" + "|".join("---" for _ in headers) + "|"]
    lines += ["| " + " | ".join(r) + " |" for r in body]
    return "\n".join(lines)


def build_report(n: int, rows: list[dict], summary: list[dict], abl: list[dict], rules: list[dict], calib: dict,
                 dvars: list[dict]) -> str:
    out = [
        "# GHOST PROTOCOL: evaluation report",
        "",
        f"{n} simulated incidents per cell (seeds {FIRST_TEST_SEED} to {FIRST_TEST_SEED + n - 1}), "
        "scripted human who approves the correct fix when it is offered, no LLM. "
        "Numbers are means with 95% confidence intervals in brackets. "
        "Likelihood tables were learned on different seeds (1000-1199).",
        "",
        "## 1. Modes compared, per scenario",
        "",
        "Recovery time = ticks from fault start until healthy (30 = never recovered). "
        "Wrong actions = actions that do not fix the true cause. "
        "Unsafe = failover that risked data consistency (the engine's validator checks the true replication lag "
        "in every mode, so this stays 0%; the standalone runbook in run_scenarios.py, which trusts noisy dashboards, "
        "reaches about 34% on S5). "
        "Brier for Mode C is computed on the team's averaged belief, which is for display, not for deciding.",
    ]
    for sc in SCENARIOS:
        out += ["", f"### {sc}: {SCENARIO_NAME[sc]}", ""]
        body = []
        for mode in MODES:
            r = next(x for x in summary if x["scenario"] == sc and x["mode"] == mode)
            body.append([f"{mode} {MODE_NAME[mode]}", fmt(r, "correct_diagnosis", pct=True), fmt(r, "recovery_time", digits=1),
                         fmt(r, "availability", pct=True), fmt(r, "unnecessary_actions"),
                         fmt(r, "escalated_to_human", pct=True), fmt(r, "unsafe_action", pct=True),
                         "n/a (no probabilities)" if mode == "A" else fmt(r, "brier_score", digits=3)])
        out.append(table(["Mode", "Right first time", "Recovery (ticks)", "Availability", "Wrong actions", "Asked a human", "Unsafe", "Brier (lower=better)"], body))

    out += ["", "## 2. Paired difference versus the runbook (same seeds)", "",
            "Positive 'right first time' and availability are good; negative recovery time is good.", ""]
    body = []
    for sc in SCENARIOS:
        for mode in ["B", "C", "D"]:
            body.append([sc, f"{mode} {MODE_NAME[mode]}",
                         signed(paired_difference(rows, sc, mode, "correct_diagnosis"), pct=True),
                         signed(paired_difference(rows, sc, mode, "recovery_time"), digits=1),
                         signed(paired_difference(rows, sc, mode, "availability"), pct=True)])
    out.append(table(["Scenario", "Mode minus runbook", "Right first time", "Recovery (ticks)", "Availability"], body))

    out += ["", "## 3. Ablation: remove one agent's evidence", "",
            "Right first time and 'asked a human' for each mode, with the named agent blind. "
            "A big drop means that agent carries information the others cannot replace.", ""]
    for mode in ["B", "C"]:
        out += ["", f"### Mode {mode}: {MODE_NAME[mode]}", ""]
        body = []
        for who in ["none"] + AGENT_IDS:
            cells = []
            for sc in SCENARIOS:
                r = next(x for x in abl if x["ablated"] == who and x["scenario"] == sc and x["mode"] == mode)
                cells.append(f"{r['correct_diagnosis_mean']:.0%} / {r['escalated_to_human_mean']:.0%}")
            body.append(["(full team)" if who == "none" else f"without {who}"] + cells)
        out.append(table(["Team"] + [f"{sc}: right / asked human" for sc in SCENARIOS], body))

    out += ["", "## 4. Decision rule variants (Mode B)", "",
            "Same engine, different rule for act / probe / ask a human.", ""]
    body = []
    for name in dict.fromkeys(r["rule"] for r in rules):
        for sc in SCENARIOS:
            r = next(x for x in rules if x["rule"] == name and x["scenario"] == sc)
            body.append([name, sc, fmt(r, "correct_diagnosis", pct=True), fmt(r, "recovery_time", digits=1),
                         fmt(r, "availability", pct=True), fmt(r, "escalated_to_human", pct=True), fmt(r, "unsafe_action", pct=True)])
    out.append(table(["Rule", "Scenario", "Right first time", "Recovery (ticks)", "Availability", "Asked a human", "Unsafe"], body))

    out += ["", "## 5. Is the belief engine honest about its confidence?", "",
            "All agents' clues pooled, ticks 7-12, 60 seeds (2000+). "
            "Average confidence should be close to accuracy.", ""]
    out.append(table(["Scenario", "Accuracy", "Average confidence", "Brier", "Uncertainty (bits)"],
                     [[sc, f"{m['accuracy']:.0%}", f"{m['avg_confidence']:.0%}", f"{m['brier']:.3f}", f"{m['entropy_bits']:.2f}"]
                      for sc, m in calib.items()]))

    out += ["", "## 6. Mode D: what the router does when two runbook rules match", "",
            "The runbook's rules can match at the same time (S2: 'traffic spike' and 'recent deploy'). "
            "The default hands the decision to the agents at that point. The naive variant applies the first matching "
            "rule, which reproduces the runbook's misfire. The default was chosen after seeing this result, so both are shown.", ""]
    body = []
    for name in D_VARIANTS:
        for sc in SCENARIOS:
            r = next(x for x in dvars if x["variant"] == name and x["scenario"] == sc)
            body.append([name, sc, fmt(r, "correct_diagnosis", pct=True), fmt(r, "recovery_time", digits=1),
                         fmt(r, "unnecessary_actions"), fmt(r, "escalated_to_human", pct=True)])
    out.append(table(["Mode D variant", "Scenario", "Right first time", "Recovery (ticks)", "Wrong actions", "Asked a human"], body))
    return "\n".join(out) + "\n"


# --------------------------------------------------------------------------
def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds", type=int, default=100)
    args = p.parse_args()
    if FIRST_TEST_SEED + args.seeds > 1000:
        raise SystemExit("Use fewer than 1000 seeds: seeds 1000+ were used to learn the likelihood tables.")
    seeds = range(FIRST_TEST_SEED, FIRST_TEST_SEED + args.seeds)
    RESULTS.mkdir(parents=True, exist_ok=True)
    t0 = time.time()

    print(f"[1/5] modes x scenarios ({args.seeds} seeds per cell)...")
    rows, summary = main_comparison(seeds)
    note = f"{args.seeds} seeds/cell, seeds {seeds.start}-{seeds.stop - 1}, D->C, oracle human, no LLM"
    (RESULTS / "official.json").write_text(json.dumps({"note": note, "summary": summary, "runs": rows}, indent=1))

    print("[2/5] ablation...")
    abl = ablation(seeds)
    (RESULTS / "official_ablation.json").write_text(json.dumps({"note": note, "rows": abl}, indent=1))

    print("[3/5] decision rule variants...")
    rules = decision_rule_variants(seeds)
    (RESULTS / "official_decision_rule.json").write_text(json.dumps({"note": note, "rows": rules}, indent=1))

    print("[4/5] Mode D variants...")
    dvars = mode_d_variants(seeds)
    (RESULTS / "official_mode_d.json").write_text(json.dumps({"note": note, "rows": dvars}, indent=1))

    print("[5/5] belief calibration...")
    calib = engine_calibration(0.5, [ScenarioId(s) for s in SCENARIOS])

    report = build_report(args.seeds, rows, summary, abl, rules, calib, dvars)
    (RESULTS / "REPORT.md").write_text(report)
    print(f"\nDone in {time.time() - t0:.0f}s. Wrote official*.json and REPORT.md to {RESULTS}")


if __name__ == "__main__":
    main()
