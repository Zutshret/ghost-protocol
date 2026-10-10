# GHOST PROTOCOL

A pretend payments platform that breaks, a team of AI agents that work out why
and negotiate a fix, and a rule-based runbook to compare them against.
Cisco Cloud AI Track: "When AI Agents Disagree".

## Setup

```bash
uv sync                      # Windows without uv on PATH: python -m uv sync
cp .env.example .env         # pick ONE provider, add your key (never commit .env)
uv run python scripts/check_llm.py   # should print "Setup OK."
uv run pytest
cd frontend && npm install && npm run build && cd ..
```

## Run the console

```bash
uv run uvicorn backend.main:app --port 8000
```

Open http://localhost:8000, pick a scenario and mode, and press **Start**.
For frontend development with hot reload, also run `cd frontend && npm run dev`
and open http://localhost:5173 (it proxies the backend).

| Scenario | What happens | Who should win |
|---|---|---|
| S1 | Clear database fault | Runbook (fast, cheap) |
| S2 | Bad deploy that looks like an attack (decoy on ~40% of seeds) | Agents |
| S3 | Dependency timeout; the Network Analyst is recruited mid-incident | Both |
| S5 | Evidence split between attack and database, every fix risky | Ask a human |

Modes: **A** runbook only · **B** agents + central aggregator · **C** agents
negotiate peer to peer · **D** runbook first, agents when the router says so.

Demo tip: S2, Mode D (then negotiation C), seed 2 (also 11, 12, 18, 22) shows the runbook blocking
traffic wrongly, the switch to agent mode, Security disagreeing with everyone,
and the team agreeing on a rollback. S5, Mode C, seed 1 shows the human approval panel.

## AGNTCY (optional)

`GHOST_AGNTCY=1` publishes the agents as cards in the AGNTCY Directory, recruits
through it, and sends one OpenTelemetry trace per run. It's off by default and falls
back to `registry.json` when Docker is off. See [docs/AGNTCY.md](docs/AGNTCY.md).

## Compare modes

```bash
uv run python eval/compare_modes.py --seeds 30                 # -> eval/results/compare.json
uv run python eval/compare_modes.py --modes B,C --ablate database
```

Results show up in the console's **results** tab.

## LLM voice (optional)

With a key in `.env` and the console's **LLM** box ticked, the agents' challenges, the
aggregator's explanation, the briefing a human reads before approving, and an end-of-run
summary are written in natural language by the LLM (`agents/voice.py`). It only changes
words: actions, votes and escalations are decided by code first, and any LLM text that
invents a number, cause or action is thrown away in favour of the template.

```bash
uv run python scripts/warm_llm_cache.py        # run once before the demo: each call takes ~4 s,
                                               # cached answers are instant
uv run python eval/evaluate_llm.py --seeds 5   # proof: same decisions with the LLM off and on
```

Free tiers allow about 15 requests a minute. `agents/llm.py` spaces calls out
(`LLM_MAX_RPM`, default 12), waits when the provider says "retry in Ns", and falls back to
templates if a call still fails, so the demo never depends on the network.

## Layout

```
shared/        types both halves agree on (hypotheses, actions, Message schema)
agents/        LLM helper, bus, agents, registry, negotiation (Mode C), recruitment
backend/       FastAPI server, incident engine (all modes), adapters to Person A's code
standins/      temporary simulator + belief engine until simulator/ and intelligence/ land
simulator/     Person A: simulator, scenarios, runbook, validator
intelligence/  Person A: likelihoods, belief engine, router, aggregator
eval/          evaluation scripts and results
frontend/      React + TypeScript + Tailwind + React Flow console
docs/          architecture, integration notes
```
