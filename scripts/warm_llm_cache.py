"""Pre-run the demo incidents with the LLM on, so the live demo replays instantly.

Each LLM call takes about 4 seconds, which would stall the console at every decision.
Answers are cached on disk (.cache/llm, per machine), so run this once on the machine
you will demo from, after setting your key in .env:

    uv run python scripts/warm_llm_cache.py

Then tick the "LLM" box in the console. The same incidents now answer from the cache.
"""

from __future__ import annotations

import sys
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from agents.llm import llm_available, llm_stats  # noqa: E402
from backend.engine import IncidentEngine  # noqa: E402

# (scenario, mode, seed): the demo walkthrough from the README, plus the other modes for each.
DEMO = [("S1", "A", 0), ("S1", "B", 0), ("S2", "D", 2), ("S2", "C", 2), ("S2", "B", 2),
        ("S3", "C", 0), ("S3", "B", 0), ("S5", "C", 1), ("S5", "B", 1), ("S5", "D", 1)]


def main() -> None:
    if not llm_available():
        raise SystemExit("No LLM key configured in .env. Run scripts/check_llm.py first.")
    t0 = time.time()
    with ThreadPoolExecutor(5) as pool:
        for (sc, mode, seed), m in zip(DEMO, pool.map(lambda c: IncidentEngine(*c, use_llm=True).run(), DEMO)):
            print(f"warmed {sc} mode {mode} seed {seed}: recovery {m.recovery_time}")
    print(f"Done in {time.time() - t0:.0f}s. {llm_stats()}")


if __name__ == "__main__":
    main()
