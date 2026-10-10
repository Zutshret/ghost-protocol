"""Proof that the LLM adds words, not risk.

Runs the same incidents twice, LLM off and LLM on, and checks that every decision
is identical: same actions in the same order, same escalations, same recovery time.
Only the wording in the ledger may differ.

    uv run python eval/evaluate_llm.py                 # 5 seeds x S2,S5 x modes B,C
    uv run python eval/evaluate_llm.py --seeds 10 --workers 8

Needs an LLM key in .env. Answers are cached in .cache/llm, so re-runs are fast.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents import voice  # noqa: E402
from agents.llm import llm_available, llm_stats, model_name  # noqa: E402
from backend.engine import IncidentEngine  # noqa: E402
from shared.types import Mode  # noqa: E402

RESULTS = Path(__file__).resolve().parent / "results"


def run(scenario: str, mode: str, seed: int, use_llm: bool) -> dict:
    t0 = time.time()
    eng = IncidentEngine(scenario, mode, seed, use_llm=use_llm, agents_mode_for_d=Mode.C)
    m = eng.run()
    words = [x.rationale for x in eng.bus.history if x.type.value in ("challenge", "escalate", "proposal") or x.content.get("event") == "summary"]
    return {
        "scenario": scenario, "mode": mode, "seed": seed, "use_llm": use_llm,
        "actions": [a.value for a in eng.applied], "escalated": m.escalated_to_human,
        "recovery_time": m.recovery_time, "correct": m.correct_diagnosis,
        "unnecessary_actions": m.unnecessary_actions, "seconds": round(time.time() - t0, 1), "words": words,
    }


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument("--seeds", type=int, default=5)
    p.add_argument("--scenarios", nargs="+", default=["S2", "S5"])
    p.add_argument("--modes", nargs="+", default=["B", "C"])
    p.add_argument("--workers", type=int, default=6)
    args = p.parse_args()
    if not llm_available():
        raise SystemExit("No LLM key configured in .env, so there is nothing to compare. Run scripts/check_llm.py.")

    cells = [(sc, mode, seed) for sc in args.scenarios for mode in args.modes for seed in range(args.seeds)]
    t0 = time.time()
    print(f"{len(cells)} incidents, LLM off then on ({args.workers} workers, model {model_name()})...")
    off = [run(*c, use_llm=False) for c in cells]
    with ThreadPoolExecutor(args.workers) as pool:
        on = list(pool.map(lambda c: run(*c, use_llm=True), cells))

    keys = ("actions", "escalated", "recovery_time", "correct", "unnecessary_actions")
    same = [all(a[k] == b[k] for k in keys) for a, b in zip(off, on)]
    changed_words = sum(a["words"] != b["words"] for a, b in zip(off, on))
    stats, vstats = llm_stats(), voice.voice_stats()
    result = {
        "model": model_name(), "runs": len(cells), "identical_decisions": sum(same),
        "runs_with_different_wording": changed_words, "voice_lines": vstats, "llm_stats": stats,
        "avg_seconds_off": round(sum(r["seconds"] for r in off) / len(off), 1),
        "avg_seconds_on": round(sum(r["seconds"] for r in on) / len(on), 1),
        "mismatches": [{"cell": cells[i], "off": {k: off[i][k] for k in keys}, "on": {k: on[i][k] for k in keys}}
                       for i, ok in enumerate(same) if not ok],
        "examples": [{"cell": cells[i], "off": off[i]["words"][-3:], "on": on[i]["words"][-3:]} for i in range(0, len(cells), max(1, len(cells) // 3))],
    }
    RESULTS.mkdir(parents=True, exist_ok=True)
    (RESULTS / "llm_proof.json").write_text(json.dumps(result, indent=1))
    lines = [
        "# LLM proof: same decisions, better words", "",
        f"Model: {model_name()}. {len(cells)} incidents ({', '.join(args.scenarios)} x modes {', '.join(args.modes)} x {args.seeds} seeds), each run with the LLM off and on.", "",
        f"- Identical decisions (actions, escalations, recovery time, correctness): **{sum(same)} of {len(cells)}**",
        f"- Runs where the ledger wording differed: {changed_words} of {len(cells)}",
        f"- Lines written by the LLM: {vstats['llm']}; templates used: {vstats['template']}; LLM lines rejected as unfaithful: {vstats['rejected']}",
        f"- Real LLM calls: {stats['calls']}; cache hits: {stats['cache_hits']}; failures (fell back to templates): {stats['failures']}",
        f"- Average seconds per incident: {result['avg_seconds_off']} off, {result['avg_seconds_on']} on (cold cache is slower; each call takes about 4 s)",
        "", "## Example ledger lines (off vs on)", "",
    ]
    for ex in result["examples"]:
        lines += [f"### {ex['cell'][0]} mode {ex['cell'][1]} seed {ex['cell'][2]}", "", "Off:", *[f"- {w}" for w in ex["off"]], "", "On:", *[f"- {w}" for w in ex["on"]], ""]
    (RESULTS / "LLM_PROOF.md").write_text("\n".join(lines))
    print(f"\nIdentical decisions: {sum(same)}/{len(cells)}  |  LLM lines {vstats['llm']}, rejected {vstats['rejected']}, failures {stats['failures']}  |  {time.time() - t0:.0f}s")
    if result["mismatches"]:
        print("MISMATCHES:", json.dumps(result["mismatches"], indent=1))


if __name__ == "__main__":
    main()
