"""Quick mode comparison across scenarios (feeds the console's Results tab).

Person A's A8 evaluation is the official one; this exists so the demo always
has charts. Runs with the scripted (oracle) human and no LLM by default.

  uv run python eval/compare_modes.py --seeds 30
  uv run python eval/compare_modes.py --modes A,B --scenarios S2 --ablate deployment
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from backend.engine import IncidentEngine  # noqa: E402

METRICS = ["recovery_time", "availability", "unnecessary_actions", "correct_diagnosis",
           "escalated_to_human", "brier_score", "llm_calls"]


def summarize(vals: list[float]) -> tuple[float, float, float]:
    """Mean with a 95% normal-approximation confidence interval."""
    m = statistics.fmean(vals)
    if len(vals) < 2:
        return m, m, m
    half = 1.96 * statistics.stdev(vals) / len(vals) ** 0.5
    return m, m - half, m + half


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--modes", default="A,B,C,D")
    ap.add_argument("--scenarios", default="S1,S2,S3,S5")
    ap.add_argument("--seeds", type=int, default=30)
    ap.add_argument("--llm", action="store_true")
    ap.add_argument("--ablate", default=None, help="remove one agent's evidence")
    ap.add_argument("--d-agents", default="C", help="agent mode Mode D hands over to (B or C)")
    ap.add_argument("--out", default=None)
    a = ap.parse_args()

    runs, summary = [], []
    for sc in a.scenarios.split(","):
        for mode in a.modes.split(","):
            rs = [IncidentEngine(sc, mode, seed, use_llm=a.llm, ablate=a.ablate, agents_mode_for_d=a.d_agents).run()
                  for seed in range(a.seeds)]
            runs += [r.model_dump(mode="json") for r in rs]
            row = {"scenario": sc, "mode": mode, "n": len(rs)}
            for k in METRICS:
                vals = [float(getattr(r, k)) for r in rs if getattr(r, k) is not None]
                if vals:
                    row[f"{k}_mean"], row[f"{k}_lo"], row[f"{k}_hi"] = (round(x, 4) for x in summarize(vals))
            summary.append(row)
            print(f"{sc} {mode}: correct={row['correct_diagnosis_mean']:.2f} rec={row['recovery_time_mean']:.1f} "
                  f"avail={row['availability_mean']:.3f} unnec={row['unnecessary_actions_mean']:.2f} "
                  f"esc={row['escalated_to_human_mean']:.2f}")

    name = a.out or ("compare" + (f"_ablate_{a.ablate}" if a.ablate else ""))
    out = Path(__file__).resolve().parent / "results" / f"{name}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    from backend.adapters import make_simulator
    note = f"{a.seeds} seeds/cell, sim={make_simulator()[1]}, D->{a.d_agents}, oracle human" + (f", ablated {a.ablate}" if a.ablate else "")
    out.write_text(json.dumps({"note": note, "summary": summary, "runs": runs}, indent=1), encoding="utf-8")
    print("wrote", out)


if __name__ == "__main__":
    main()
