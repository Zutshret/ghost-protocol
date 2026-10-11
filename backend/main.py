"""FastAPI backend (A7): start runs, stream events over a websocket, take human decisions.

Run:  uv run uvicorn backend.main:app --reload --port 8000

  GET  /api/meta                      roster, scenarios, modes, LLM status
  POST /api/runs                      {scenario, mode, seed, use_llm, tick_delay, agents_mode_for_d, ablate}
  GET  /api/runs/{run_id}             status + metrics + full message history
  POST /api/runs/{run_id}/human       {decision: approve|reject, action}
  POST /api/runs/{run_id}/stop
  GET  /api/results                   saved evaluation results (eval/results/*.json)
  WS   /ws/runs/{run_id}              history replay, then live Messages (shared schema)
"""

from __future__ import annotations

import asyncio
import json
import threading
from pathlib import Path

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agents.agent_base import load_registry
from agents.bus import InMemoryBus, WebSocketForwarder
from agents.llm import llm_available, llm_stats, model_name
from backend import adapters
from backend.engine import IncidentEngine
from shared.types import Action, Mode, ScenarioId

ROOT = Path(__file__).resolve().parent.parent
RESULTS_DIR = ROOT / "eval" / "results"
FRONTEND_DIST = ROOT / "frontend" / "dist"
HUMAN_TIMEOUT_S = 600

app = FastAPI(title="GHOST PROTOCOL")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


class RunRequest(BaseModel):
    scenario: ScenarioId = ScenarioId.S2
    mode: Mode = Mode.D
    seed: int = 1
    use_llm: bool = False
    tick_delay: float = 0.8
    agents_mode_for_d: Mode = Mode.C
    escalate_on_conflict: bool = True
    ablate: str | None = None


class HumanReply(BaseModel):
    decision: str  # approve | reject
    action: Action = Action.NOOP
    note: str = ""


class Run:
    def __init__(self, req: RunRequest, loop: asyncio.AbstractEventLoop) -> None:
        self.req = req
        self.bus = InMemoryBus()
        self.forwarder = WebSocketForwarder(self.bus, loop)
        self.status = "running"
        self.metrics: dict | None = None
        self.error: str | None = None
        self.stop = threading.Event()
        self._human_event = threading.Event()
        self._human_reply: dict | None = None
        self.pending_escalation: dict | None = None
        self.engine = IncidentEngine(
            req.scenario, req.mode, req.seed, bus=self.bus, use_llm=req.use_llm, human=self._ask_human,
            tick_delay=req.tick_delay, agents_mode_for_d=req.agents_mode_for_d,
            escalate_on_conflict=req.escalate_on_conflict, ablate=req.ablate,
            should_stop=self.stop.is_set,
        )
        self.id = self.engine.run_id

    def _ask_human(self, content: dict, engine: IncidentEngine) -> dict:
        self.status, self.pending_escalation = "waiting_for_human", content
        self._human_event.clear()
        while not self._human_event.wait(0.25):
            if self.stop.is_set():
                return {"decision": "reject", "action": "noop", "note": "run stopped"}
        self.status, self.pending_escalation = "running", None
        return self._human_reply or {"decision": "reject", "action": "noop"}

    def answer(self, reply: HumanReply) -> None:
        self._human_reply = reply.model_dump(mode="json")
        self._human_event.set()

    def thread_main(self) -> None:
        try:
            self.metrics = self.engine.run().model_dump(mode="json")
            self.status = "stopped" if self.stop.is_set() else "finished"
        except Exception as exc:  # noqa: BLE001 - surface to the console
            self.status, self.error = "error", f"{type(exc).__name__}: {exc}"
            from shared.types import Message, MessageType

            self.bus.publish(Message(run_id=self.id, tick=getattr(self.engine, "tick", 0), sender="system",
                                     type=MessageType.TELEMETRY, content={"event": "error", "error": self.error},
                                     rationale=f"Run crashed: {self.error}"))


RUNS: dict[str, Run] = {}


def _get(run_id: str) -> Run:
    if run_id not in RUNS:
        raise HTTPException(404, f"unknown run {run_id}")
    return RUNS[run_id]


@app.get("/api/meta")
def meta() -> dict:
    sim, sim_src = adapters.make_simulator()
    _, eng_src = adapters.make_belief_engine()
    return {
        "roster": [s.public() for s in load_registry().values()],
        "scenarios": [s.value for s in ScenarioId],
        "modes": [m.value for m in Mode],
        "actions": [a.value for a in Action],
        "llm": {"available": llm_available(), "model": model_name() if llm_available() else None, **llm_stats()},
        "simulator": sim_src, "belief_engine": eng_src,
    }


@app.post("/api/runs")
async def start_run(req: RunRequest) -> dict:
    for r in RUNS.values():  # one live demo at a time keeps the console simple
        if r.status in ("running", "waiting_for_human"):
            r.stop.set()
    run = Run(req, asyncio.get_running_loop())
    RUNS[run.id] = run
    threading.Thread(target=run.thread_main, daemon=True, name=f"run-{run.id}").start()
    return {"run_id": run.id}


@app.get("/api/runs/{run_id}")
def get_run(run_id: str) -> dict:
    r = _get(run_id)
    return {"run_id": r.id, "status": r.status, "metrics": r.metrics, "error": r.error,
            "pending_escalation": r.pending_escalation, "request": r.req.model_dump(mode="json"),
            "messages": [m.model_dump(mode="json") for m in r.bus.history]}


@app.post("/api/runs/{run_id}/human")
def human(run_id: str, reply: HumanReply) -> dict:
    r = _get(run_id)
    if r.status != "waiting_for_human":
        raise HTTPException(409, "this run is not waiting for a human")
    r.answer(reply)
    return {"ok": True}


@app.post("/api/runs/{run_id}/stop")
def stop(run_id: str) -> dict:
    _get(run_id).stop.set()
    return {"ok": True}


@app.get("/api/results")
def results() -> dict:
    out = {}
    if RESULTS_DIR.exists():
        for p in sorted(RESULTS_DIR.glob("*.json")):
            try:
                out[p.stem] = json.loads(p.read_text(encoding="utf-8"))
            except json.JSONDecodeError:
                continue
    return out


@app.websocket("/ws/runs/{run_id}")
async def ws_run(ws: WebSocket, run_id: str) -> None:
    await ws.accept()
    if run_id not in RUNS:
        await ws.close(code=4404)
        return
    r = RUNS[run_id]
    q = r.forwarder.add_client()
    try:
        replay = [m.model_dump(mode="json") for m in list(r.bus.history)]
        seen = max((m["id"] for m in replay), default=0)
        for m in replay:
            await ws.send_json(m)
        while True:
            m = await q.get()
            if m["id"] > seen:
                await ws.send_json(m)
    except (WebSocketDisconnect, RuntimeError):
        pass
    finally:
        r.forwarder.remove_client(q)


# Serve the built console (npm run build) from the same port, if present.
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/")
    def index() -> FileResponse:
        return FileResponse(FRONTEND_DIST / "index.html")
