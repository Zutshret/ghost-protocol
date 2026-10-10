import { useMemo, useState } from "react";
import AgentRoster from "./components/AgentRoster";
import ApprovalPanel from "./components/ApprovalPanel";
import DetailDrawer from "./components/DetailDrawer";
import Ledger from "./components/Ledger";
import Results from "./components/Results";
import ServiceGraph from "./components/ServiceGraph";
import type { AgentSpec, Msg } from "./types";
import { useRun, type RunConfig } from "./useRun";

const SCENARIO_HELP: Record<string, string> = {
  S1: "Clear database fault (runbook should win)",
  S2: "Bad deploy that looks like an attack",
  S3: "Dependency timeout (specialist recruited)",
  S5: "Ambiguous + high-stakes (ask a human)",
};
const MODE_HELP: Record<string, string> = {
  A: "Runbook only",
  B: "Agents + central aggregator",
  C: "Agents negotiate peer-to-peer",
  D: "Hybrid: runbook first, then agents",
};

function ModeIndicator({ mode }: { mode: { mode: string; reason: string } | null }) {
  const m = mode?.mode ?? "idle";
  const style =
    m === "runbook" ? "bg-slate-600/30 border-slate-400 text-slate-100"
      : m === "agents" ? "bg-violet-600/30 border-violet-400 text-violet-100"
        : m === "resolved" ? "bg-emerald-600/30 border-emerald-400 text-emerald-100"
          : "bg-slate-800 border-slate-700 text-slate-400";
  const label = m === "runbook" ? "RUNBOOK MODE · deterministic" : m === "agents" ? "AGENT MODE · probabilistic"
    : m === "resolved" ? "RESOLVED" : "MONITORING";
  return (
    <div className={`flex items-center gap-3 rounded-lg border px-3 py-1.5 ${style} min-w-0`}>
      <span className="font-bold text-xs tracking-wider whitespace-nowrap">{label}</span>
      {mode?.reason && <span className="text-xs opacity-80 truncate" title={mode.reason}>{mode.reason}</span>}
    </div>
  );
}

export default function App() {
  const { runId, messages, derived, meta, connected, start, stop, answer } = useRun();
  const [tab, setTab] = useState<"live" | "results">("live");
  const [cfg, setCfg] = useState<RunConfig>({
    scenario: "S2", mode: "D", seed: 2, use_llm: false, tick_delay: 0.8,
    agents_mode_for_d: "C", escalate_on_conflict: false, ablate: null,
  });
  const [selected, setSelected] = useState<Msg | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const roster = useMemo(() => new Map<string, AgentSpec>(derived.agents.map((a) => [a.spec.id, a.spec])), [derived.agents]);
  const running = !!runId && !derived.metrics && !derived.error;
  const set = (k: keyof RunConfig, v: any) => setCfg((c) => ({ ...c, [k]: v }));
  const err = derived.availability.length ? derived.services : null;
  const lastTel = [...messages].reverse().find((m) => m.type === "telemetry" && m.content.services && !m.content.event);

  return (
    <div className="h-full flex flex-col">
      {/* header */}
      <header className="flex flex-wrap items-center gap-3 px-4 py-2 border-b border-slate-800 bg-slate-950">
        <div className="flex items-baseline gap-2">
          <span className="font-black tracking-[0.2em] text-slate-100">GHOST PROTOCOL</span>
          <span className="text-[11px] text-slate-500">when AI agents disagree</span>
        </div>
        <nav className="flex gap-1 text-xs">
          {(["live", "results"] as const).map((t) => (
            <button key={t} onClick={() => setTab(t)} className={`px-2 py-1 rounded ${tab === t ? "bg-slate-800 text-white" : "text-slate-400"}`}>{t}</button>
          ))}
        </nav>
        <div className="flex flex-wrap items-center gap-2 text-xs ml-auto">
          <select title={SCENARIO_HELP[cfg.scenario]} value={cfg.scenario} onChange={(e) => set("scenario", e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1">
            {(meta?.scenarios ?? ["S1", "S2", "S3", "S5"]).map((s: string) => <option key={s} value={s}>{s} · {SCENARIO_HELP[s] ?? ""}</option>)}
          </select>
          <select value={cfg.mode} onChange={(e) => set("mode", e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1">
            {(meta?.modes ?? ["A", "B", "C", "D"]).map((m: string) => <option key={m} value={m}>Mode {m} · {MODE_HELP[m]}</option>)}
          </select>
          {cfg.mode === "D" && (
            <select value={cfg.agents_mode_for_d} onChange={(e) => set("agents_mode_for_d", e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1" title="Which agent mode D hands over to">
              <option value="B">then aggregator (B)</option>
              <option value="C">then negotiation (C)</option>
            </select>
          )}
          <label className="flex items-center gap-1">seed
            <input type="number" value={cfg.seed} onChange={(e) => set("seed", +e.target.value)} className="w-14 bg-slate-900 border border-slate-700 rounded px-1 py-1" />
          </label>
          <label className="flex items-center gap-1" title="tick delay (seconds)">speed
            <select value={cfg.tick_delay} onChange={(e) => set("tick_delay", +e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-1 py-1">
              <option value={1.5}>slow</option><option value={0.8}>demo</option><option value={0.25}>fast</option><option value={0}>instant</option>
            </select>
          </label>
          <label className={`flex items-center gap-1 ${meta?.llm?.available ? "" : "opacity-50"}`} title={meta?.llm?.available ? meta.llm.model : "no LLM key in .env: agents use measured levels + template reasons"}>
            <input type="checkbox" disabled={!meta?.llm?.available} checked={cfg.use_llm} onChange={(e) => set("use_llm", e.target.checked)} /> LLM
          </label>
          <select value={cfg.ablate ?? ""} onChange={(e) => set("ablate", e.target.value || null)} className="bg-slate-900 border border-slate-700 rounded px-1 py-1" title="Ablation: remove one agent's evidence">
            <option value="">no ablation</option>
            {derived.agents.map((a) => <option key={a.spec.id} value={a.spec.id}>ablate {a.spec.id}</option>)}
          </select>
          {running
            ? <button onClick={stop} className="px-3 py-1 rounded bg-slate-700 hover:bg-slate-600 font-semibold">Stop</button>
            : <button onClick={() => { setTab("live"); setSelected(null); start(cfg); }} className="px-3 py-1 rounded bg-violet-600 hover:bg-violet-500 font-semibold">Start</button>}
        </div>
      </header>

      {meta?.error && <div className="bg-red-900/50 text-red-200 text-sm px-4 py-1">Backend not reachable. Start it: <span className="mono">uv run uvicorn backend.main:app --port 8000</span></div>}

      {tab === "results" ? <Results /> : (
        <main className="flex-1 min-h-0 grid grid-cols-1 lg:grid-cols-[1fr_440px] xl:grid-cols-[1fr_520px]">
          <section className="min-h-0 overflow-y-auto p-3 space-y-3">
            <div className="flex items-center gap-3">
              <ModeIndicator mode={derived.mode} />
              <div className="ml-auto flex gap-4 text-xs mono text-slate-400 whitespace-nowrap">
                <span>tick <b className="text-slate-100">{derived.tick}</b>/30</span>
                {lastTel && <span>errors <b className={lastTel.content.error_rate > 0.03 ? "text-red-400" : "text-emerald-400"}>{(lastTel.content.error_rate * 100).toFixed(1)}%</b></span>}
                {lastTel && <span>latency <b className={lastTel.content.latency_ms > 300 ? "text-red-400" : "text-emerald-400"}>{Math.round(lastTel.content.latency_ms)}ms</b></span>}
                {lastTel?.content.lockout > 0 && <span className="text-orange-400">customer lockout!</span>}
                {derived.agntcy?.enabled && (
                  <span className={derived.agntcy.directory === "ok" ? "text-emerald-400" : "text-amber-400"}
                    title="AGNTCY Directory + Observe (GHOST_AGNTCY=1)">AGNTCY {derived.agntcy.directory === "ok" ? "on" : "fallback"}</span>
                )}
                <span className={connected ? "text-emerald-500" : "text-slate-600"}>● {connected ? "live" : "idle"}</span>
              </div>
            </div>
            <div className="rounded-lg border border-slate-800 bg-slate-900/40">
              <div className="px-3 pt-2 text-xs text-slate-400 flex gap-2">
                <span className="font-semibold text-slate-200">Payments platform</span>
                {derived.start && <span>scenario {derived.start.content.scenario} · mode {derived.start.content.mode} · seed {derived.start.content.seed} · sim: {derived.start.content.simulator}</span>}
              </div>
              <ServiceGraph services={err ?? derived.services} />
            </div>
            {derived.lastAction && (
              <button onClick={() => setSelected(derived.lastAction)} className="w-full text-left rounded-lg border border-red-500/40 bg-red-500/5 px-3 py-2 text-sm hover:bg-red-500/10">
                <span className="text-xs text-red-300 font-semibold mr-2">LAST ACTION · t{derived.lastAction.tick}</span>
                <span className="mono">{derived.lastAction.content.action}</span>
                <span className="text-slate-400"> by {derived.lastAction.sender}: {derived.lastAction.rationale}</span>
                <span className="text-xs text-slate-500"> (click for provenance)</span>
              </button>
            )}
            {derived.metrics && (
              <div className="grid grid-cols-3 md:grid-cols-6 gap-2">
                {[
                  ["Correct diagnosis", derived.metrics.correct_diagnosis ? "yes" : "no", derived.metrics.correct_diagnosis],
                  ["Recovery", `${derived.metrics.recovery_time} ticks`, derived.metrics.recovery_time < 15],
                  ["Availability", `${(derived.metrics.availability * 100).toFixed(1)}%`, derived.metrics.availability > 0.95],
                  ["Unnecessary actions", derived.metrics.unnecessary_actions, derived.metrics.unnecessary_actions === 0],
                  ["Asked human", derived.metrics.escalated_to_human ? "yes" : "no", true],
                  ["LLM calls", derived.metrics.llm_calls, true],
                ].map(([k, v, good]) => (
                  <div key={k as string} className={`rounded-lg border p-2 ${good ? "border-emerald-700/50" : "border-red-700/60"}`}>
                    <div className="text-[10px] text-slate-500 uppercase">{k}</div>
                    <div className="text-lg font-semibold">{String(v)}</div>
                  </div>
                ))}
              </div>
            )}
            {derived.error && <div className="rounded border border-red-600 bg-red-950 p-2 text-sm text-red-200">{derived.error}</div>}
            <div>
              <div className="text-xs text-slate-400 mb-2 flex gap-2">
                <span className="font-semibold text-slate-200">Agent roster</span>
                <span>live beliefs over 4 hypotheses · click an agent to filter the ledger</span>
              </div>
              <AgentRoster agents={derived.agents} cids={derived.agntcy?.cids} onSelect={(id) => setAgentFilter(id === agentFilter ? null : id)} />
            </div>
          </section>
          <aside className="min-h-0 border-l border-slate-800 bg-slate-950 h-[60vh] lg:h-auto">
            <Ledger messages={messages} roster={roster} selected={selected?.id ?? null} onSelect={setSelected}
              agentFilter={agentFilter} clearAgentFilter={() => setAgentFilter(null)} traceId={derived.agntcy?.trace_id} />
          </aside>
        </main>
      )}

      {selected && <DetailDrawer msg={selected} byId={derived.byId} roster={roster} onClose={() => setSelected(null)} onSelect={setSelected} />}
      {derived.escalation && (
        <ApprovalPanel key={derived.escalation.id} esc={derived.escalation} onAnswer={answer}
          onShowProvenance={() => setSelected(derived.escalation)} />
      )}
    </div>
  );
}
