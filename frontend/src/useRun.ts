import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import type { AgentSpec, Metrics, Msg, Option, ServiceState } from "./types";

export interface RunConfig {
  scenario: string;
  mode: string;
  seed: number;
  use_llm: boolean;
  tick_delay: number;
  agents_mode_for_d: string;
  escalate_on_conflict: boolean;
  ablate: string | null;
}

export interface AgentView {
  spec: AgentSpec;
  active: boolean;
  recruitedWhy?: string;
  recruitedMidIncident?: boolean;
  belief?: Record<string, number>;
  prevBelief?: Record<string, number>;
  evidence?: Record<string, string>;
  values?: Record<string, number>;
  preferred?: string;
  rationale?: string;
  status?: string;
  lastType?: string;
}

export interface Derived {
  start?: Msg;
  tick: number;
  services: Record<string, ServiceState>;
  mode: { mode: string; reason: string; tick: number } | null;
  agents: AgentView[];
  escalation: Msg | null;
  metrics: Metrics | null;
  error: string | null;
  availability: number[];
  lastAction: Msg | null;
  byId: Map<number, Msg>;
}

export function useRun() {
  const [runId, setRunId] = useState<string | null>(null);
  const [messages, setMessages] = useState<Msg[]>([]);
  const [roster, setRoster] = useState<AgentSpec[]>([]);
  const [meta, setMeta] = useState<any>(null);
  const [connected, setConnected] = useState(false);
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    fetch("/api/meta")
      .then((r) => r.json())
      .then((m) => {
        setMeta(m);
        setRoster(m.roster);
      })
      .catch(() => setMeta({ error: "backend not reachable on :8000" }));
  }, []);

  useEffect(() => {
    if (!runId) return;
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const ws = new WebSocket(`${proto}://${location.host}/ws/runs/${runId}`);
    wsRef.current = ws;
    const buf: Msg[] = [];
    let raf = 0;
    const flush = () => {
      raf = 0;
      const batch = buf.splice(0);
      setMessages((prev) => {
        const seen = prev.length ? prev[prev.length - 1].id : 0;
        return prev.concat(batch.filter((m) => m.id > seen));
      });
    };
    ws.onopen = () => setConnected(true);
    ws.onclose = () => setConnected(false);
    ws.onmessage = (e) => {
      buf.push(JSON.parse(e.data));
      if (!raf) raf = requestAnimationFrame(flush);
    };
    return () => {
      ws.close();
      if (raf) cancelAnimationFrame(raf);
    };
  }, [runId]);

  const start = useCallback(async (cfg: RunConfig) => {
    setMessages([]);
    const r = await fetch("/api/runs", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(cfg),
    });
    const j = await r.json();
    setRunId(j.run_id);
  }, []);

  const stop = useCallback(async () => {
    if (runId) await fetch(`/api/runs/${runId}/stop`, { method: "POST" });
  }, [runId]);

  const answer = useCallback(
    async (decision: "approve" | "reject", action: string) => {
      if (!runId) return;
      await fetch(`/api/runs/${runId}/human`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ decision, action, note: "via console" }),
      });
    },
    [runId],
  );

  const derived = useMemo(() => derive(messages, roster), [messages, roster]);
  return { runId, messages, derived, meta, connected, start, stop, answer };
}

const STATUS: Record<string, (m: Msg) => string> = {
  belief: (m) => `believes ${m.content.top} (${pct(m.content.confidence)})`,
  proposal: (m) => `proposes ${m.content.action}`,
  challenge: (m) => `challenges @${m.content.target}`,
  evidence: (m) => `shares evidence with @${m.content.to}`,
  accept: (m) => `accepts ${m.content.action}`,
  reject: (m) => `rejects ${m.content.action}`,
  veto: (m) => `VETOES ${m.content.action}`,
};

export const pct = (x: number | undefined | null) => (x == null ? "-" : `${Math.round(x * 100)}%`);

function derive(messages: Msg[], roster: AgentSpec[]): Derived {
  const byId = new Map<number, Msg>();
  let start: Msg | undefined;
  let services: Record<string, ServiceState> = {};
  let mode: Derived["mode"] = null;
  let escalation: Msg | null = null;
  let metrics: Metrics | null = null;
  let error: string | null = null;
  let lastAction: Msg | null = null;
  let tick = 0;
  const availability: number[] = [];
  const specs = new Map<string, AgentSpec>(roster.map((s) => [s.id, s]));
  const views = new Map<string, AgentView>();

  for (const m of messages) {
    byId.set(m.id, m);
    tick = Math.max(tick, m.tick);
    if (m.type === "telemetry") {
      if (m.content.event === "start") {
        start = m;
        for (const s of m.content.roster as AgentSpec[]) specs.set(s.id, s);
        services = m.content.services ?? services;
      } else if (m.content.event === "end") metrics = m.content.metrics;
      else if (m.content.event === "error") error = m.content.error;
      else if (m.content.services) {
        services = m.content.services;
        availability.push(m.content.availability);
      }
      continue;
    }
    if (m.type === "mode_switch") mode = { mode: m.content.mode, reason: m.rationale, tick: m.tick };
    if (m.type === "escalate") escalation = m;
    if (m.type === "human_response") escalation = null;
    if (m.type === "action") lastAction = m;
    if (m.type === "recruit") {
      const v = views.get(m.content.agent) ?? ({} as AgentView);
      views.set(m.content.agent, { ...v, active: true, recruitedWhy: m.rationale, recruitedMidIncident: !m.content.initial });
    }
    if (specs.has(m.sender)) {
      const v = views.get(m.sender) ?? ({ active: true } as AgentView);
      const nv: AgentView = { ...v, lastType: m.type, status: STATUS[m.type]?.(m) ?? m.type };
      if (m.type === "belief") {
        nv.prevBelief = v.belief;
        nv.belief = m.content.belief;
        nv.evidence = m.content.evidence;
        nv.values = m.content.values;
        nv.preferred = m.content.preferred_action;
        nv.rationale = m.rationale;
      }
      views.set(m.sender, nv);
    }
  }
  const agents: AgentView[] = [...specs.values()].map((spec) => ({
    ...(views.get(spec.id) ?? { active: false }),
    spec,
    active: views.get(spec.id)?.active ?? false,
  }));
  return { start, tick, services, mode, agents, escalation, metrics, error, availability, lastAction, byId };
}

export type EscalationOptions = Option[];
