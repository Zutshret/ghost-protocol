# AGNTCY integration (light)

Optional and **off by default**. With it off (or with Docker off), GHOST PROTOCOL
behaves exactly as before: recruitment reads `agents/registry.json` and no traces
are sent. Evaluation (`eval/evaluate.py`) is unaffected unless you set the env var.

## What it does

| Piece | With `GHOST_AGNTCY=1` | Fallback |
|---|---|---|
| **Directory** | Every agent in `registry.json` is published as an OASF 0.8.0 agent card to the AGNTCY Directory (`dir-apiserver` v1.0.0). Each agent gets a record ID (CID), shown as an **AGNTCY ✓** badge on its roster card. | none needed |
| **Recruitment** | Mid-incident, the Network Analyst is found by **searching the Directory** for capability `dependency_timeout_analysis`. The ledger says "AGNTCY Directory search (record …)". | `registry.json lookup (AGNTCY Directory unavailable)` |
| **Observe** | One OpenTelemetry trace per run (`incident.run`), with one span per bus message (`bus.belief`, `bus.challenge`, `bus.veto`, …), sent over OTLP. The trace ID shows in the ledger header. | no spans |

Card format: the Directory validates `skills` and `domains` against the OASF taxonomy,
so our own capability tags live in `annotations` (`ghost.capabilities`,
`ghost.features`, …). The cards use the valid OASF names
`agent_orchestration/agent_coordination` and `technology/networking`. Directory search
can't filter on annotations, so we search by author (`ghost-protocol`) and match the
capability in our code.

## Run it (Windows/macOS, Docker Desktop running)

The Directory and the trace pipeline come from Cisco's
[coffeeAgntcy](https://github.com/agntcy/coffeeAgntcy) Docker setups.

```bash
git clone --depth 1 https://github.com/agntcy/coffeeAgntcy.git
cd coffeeAgntcy/coffeeAGNTCY/coffee_agents

# 1. Directory (+ Postgres, Zot). WORKFLOW_API_KEY is required by that compose file
#    but unused by these services.
cd lungo && WORKFLOW_API_KEY=unused docker compose --profile recruiter up -d dir-api-server && cd ..

# 2. Trace pipeline: OTel collector -> ClickHouse -> Grafana (http://localhost:3001, admin/admin).
#    Do NOT start corto's exchange-server: it also wants port 8000.
cd corto && docker compose up -d clickhouse-server otel-collector grafana && cd ..
```

Then, in ghost-protocol:

```bash
uv sync --extra agntcy                 # OpenTelemetry packages (optional extra)
GHOST_AGNTCY=1 uv run uvicorn backend.main:app --port 8000
# PowerShell: $env:GHOST_AGNTCY="1"; uv run uvicorn backend.main:app --port 8000
```

The first run publishes the 6 cards (about 10 s), and later runs reuse them. Use
**S3** to see recruitment through the Directory.

Settings: `GHOST_DIRCTL` (how to run dirctl; the default is the `dir-ctl` Docker
image on the `lungo_default` network) and `GHOST_OTLP_ENDPOINT` (default
`http://localhost:4318`).

## Check it

```bash
# cards in the Directory
docker run --rm --network lungo_default ghcr.io/agntcy/dir-ctl:v1.0.0 \
  --server-addr dir-api-server:8888 --auth-mode insecure search --author ghost-protocol
# spans for a run (trace ID from the ledger header)
curl -s -u admin:admin http://localhost:8123/ --data-binary \
  "SELECT SpanName, count() FROM otel_traces WHERE TraceId='<trace id>' GROUP BY SpanName"
```

## What we did not do (and why)

Agents still talk over the in-memory bus, not A2A over SLIM. They run in one
process, so SLIM would add risk without a visible benefit before the deadline.
The spike showed it working in coffeeAgntcy's corto demo (one trace spanning
exchange → SLIM → farm). Swapping it in is the natural next step: the `Bus`
interface is publish/subscribe only.
