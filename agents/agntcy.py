"""AGNTCY "light" integration (B10). Optional, off by default.

Turn it on with GHOST_AGNTCY=1. Then:
  1. Directory: every agent in registry.json is published as an OASF agent card
     to the AGNTCY Directory (dir-apiserver), and mid-incident recruitment looks
     agents up there by capability. Each agent gets the card's record ID (CID).
  2. Observe: every bus message becomes an OpenTelemetry span under one trace
     per run, exported over OTLP (e.g. to the coffeeAgntcy collector -> ClickHouse
     -> Grafana).

Everything degrades gracefully: Docker off, Directory down, or OpenTelemetry not
installed -> recruitment reads registry.json and no traces are sent. Nothing
here can fail a run. Evaluation stays fast because it is off unless the env var is set.

Settings (env):
  GHOST_AGNTCY=1           turn it on
  GHOST_DIRCTL             command that runs dirctl (default: the dir-ctl Docker
                           image on the lungo_default network, as in coffeeAgntcy)
  GHOST_OTLP_ENDPOINT      OTLP/HTTP collector (default http://localhost:4318)
"""

from __future__ import annotations

import json
import os
import re
import shlex
import subprocess
import threading
from concurrent.futures import ThreadPoolExecutor
from typing import Any

from shared.types import Message

DEFAULT_DIRCTL = (
    "docker run --rm -i --network lungo_default ghcr.io/agntcy/dir-ctl:v1.0.0 "
    "--server-addr dir-api-server:8888 --auth-mode insecure"
)
AUTHOR = "ghost-protocol"
DIRCTL_TIMEOUT_S = 30
# The Directory validates skills/domains against the OASF taxonomy, so custom
# capability tags live in annotations; these two are valid OASF names.
OASF_SKILL = "agent_orchestration/agent_coordination"
OASF_DOMAIN = "technology/networking"

_lock = threading.Lock()
_cids: dict[str, str] = {}  # agent id -> record CID (from publishing)
_status: dict[str, Any] = {"published": False, "directory": "not tried", "error": None}


def enabled() -> bool:
    return os.getenv("GHOST_AGNTCY") == "1"


def status() -> dict[str, Any]:
    with _lock:
        return {"enabled": enabled(), **_status, "cids": dict(_cids)}


# --------------------------------------------------------------------------
# Directory
# --------------------------------------------------------------------------
def card_for(spec) -> dict[str, Any]:
    """An OASF 0.8.0 agent card for one registry entry (deterministic, so the CID is stable)."""
    return {
        "schema_version": "0.8.0",
        "name": f"{AUTHOR}/{spec.id}",
        "version": "1.0.0",
        "description": f"{spec.name}: {spec.role}. Goal: {spec.goal}",
        "authors": [AUTHOR],
        "created_at": "2026-10-10T00:00:00Z",
        "skills": [{"name": OASF_SKILL}],
        "domains": [{"name": OASF_DOMAIN}],
        "annotations": {
            "ghost.id": spec.id,
            "ghost.capabilities": ",".join(spec.capabilities),
            "ghost.features": ",".join(spec.features),
            "ghost.core": str(spec.core).lower(),
            "ghost.safety_critical": str(spec.safety_critical).lower(),
        },
    }


def _dirctl(args: list[str], stdin: str | None = None) -> str | None:
    cmd = shlex.split(os.getenv("GHOST_DIRCTL", DEFAULT_DIRCTL), posix=os.name != "nt") + args
    env = dict(os.environ, MSYS_NO_PATHCONV="1")
    try:
        out = subprocess.run(cmd, input=stdin, capture_output=True, text=True,
                             timeout=DIRCTL_TIMEOUT_S, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        _set_error(f"dirctl not runnable: {type(exc).__name__}")
        return None
    if out.returncode != 0:
        _set_error((out.stderr or out.stdout).strip().splitlines()[-1][:200] if (out.stderr or out.stdout) else "dirctl failed")
        return None
    return out.stdout


def _set_error(msg: str) -> None:
    with _lock:
        _status["directory"] = "unavailable"
        _status["error"] = msg


def _push(spec) -> tuple[str, str | None]:
    out = _dirctl(["push", "--stdin"], stdin=json.dumps(card_for(spec)))
    m = re.search(r"CID:\s*(\S+)", out or "")
    return spec.id, (m.group(1) if m else None)


def publish_registry(specs) -> dict[str, str]:
    """Publish every agent card once per process. Returns {agent_id: CID} (empty if unavailable)."""
    if not enabled():
        return {}
    with _lock:
        if _status["published"]:
            return dict(_cids)
    with ThreadPoolExecutor(6) as pool:
        results = list(pool.map(_push, specs))
    with _lock:
        _status["published"] = True
        for agent_id, cid in results:
            if cid:
                _cids[agent_id] = cid
        if _cids:
            _status["directory"], _status["error"] = "ok", None
        return dict(_cids)


def lookup(capability: str) -> list[tuple[str, str | None]] | None:
    """Agents in the Directory that advertise `capability`: [(agent_id, CID)].

    None means the Directory could not be asked (caller falls back to registry.json).
    """
    if not enabled():
        return None
    out = _dirctl(["search", "--author", AUTHOR, "--format", "record", "-o", "json"])
    if out is None:
        return None
    try:
        records = json.loads(out[out.index("["):])
    except ValueError:
        _set_error("could not parse Directory search output")
        return None
    found = []
    for rec in records:
        ann = (rec.get("data") or rec).get("annotations", {})
        if capability in ann.get("ghost.capabilities", "").split(","):
            agent_id = ann.get("ghost.id")
            found.append((agent_id, _cids.get(agent_id) or _cid_by_name(f"{AUTHOR}/{agent_id}")))
    with _lock:
        _status["directory"] = "ok"
    return found


def _cid_by_name(name: str) -> str | None:
    out = _dirctl(["search", "--name", name, "-o", "json"])
    try:
        cids = json.loads(out[out.index("["):]) if out else []
    except ValueError:
        return None
    return cids[0] if cids else None


# --------------------------------------------------------------------------
# Observe: one OpenTelemetry trace per run, one span per bus message
# --------------------------------------------------------------------------
_provider = None


def _tracer():
    global _provider
    try:
        from opentelemetry import trace
        from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
        from opentelemetry.sdk.resources import Resource
        from opentelemetry.sdk.trace import TracerProvider
        from opentelemetry.sdk.trace.export import BatchSpanProcessor
    except ImportError:
        return None, None
    with _lock:
        if _provider is None:
            endpoint = os.getenv("GHOST_OTLP_ENDPOINT", "http://localhost:4318").rstrip("/") + "/v1/traces"
            _provider = TracerProvider(resource=Resource.create({"service.name": "ghost-protocol"}))
            _provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter(endpoint=endpoint, timeout=5)))
    return _provider.get_tracer("ghost-protocol.bus"), trace


class RunTrace:
    """Root span for one incident run; every bus message is a child span."""

    def __init__(self, run_id: str, attrs: dict[str, Any]) -> None:
        self.trace_id: str | None = None
        self._root = None
        tracer, trace = _tracer() if enabled() else (None, None)
        if tracer is None:
            return
        self._tracer, self._trace = tracer, trace
        self._root = tracer.start_span("incident.run", attributes={"ghost.run_id": run_id, **attrs})
        self._ctx = trace.set_span_in_context(self._root)
        self.trace_id = format(self._root.get_span_context().trace_id, "032x")

    def on_message(self, m: Message) -> None:
        if self._root is None:
            return
        span = self._tracer.start_span(f"bus.{m.type.value}", context=self._ctx, attributes={
            "ghost.msg_id": m.id, "ghost.sender": m.sender, "ghost.tick": m.tick,
            "ghost.type": m.type.value, "ghost.rationale": m.rationale[:300],
        })
        span.end()

    def end(self, attrs: dict[str, Any] | None = None) -> None:
        if self._root is None:
            return
        for k, v in (attrs or {}).items():
            self._root.set_attribute(k, v)
        self._root.end()
        if _provider is not None:
            _provider.force_flush(timeout_millis=3000)
