import { useEffect, useMemo, useState } from "react";
import AgentRoster from "./components/AgentRoster";
import ApprovalPanel from "./components/ApprovalPanel";
import DetailDrawer from "./components/DetailDrawer";
import Header from "./components/Header";
import Ledger from "./components/Ledger";
import Results from "./components/Results";
import ServiceGraph from "./components/ServiceGraph";
import type { AgentSpec, Msg } from "./types";
import { useRun, type RunConfig } from "./useRun";

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
  const [, setHelp] = useState(false);

  // Shareable demo links: ?scenario=S5&mode=C&seed=1&speed=0&autorun=1
  useEffect(() => {
    const q = new URLSearchParams(location.search);
    const next = { ...cfg };
    if (q.get("scenario")) next.scenario = q.get("scenario")!;
    if (q.get("mode")) next.mode = q.get("mode")!;
    if (q.get("seed")) next.seed = Number(q.get("seed"));
    if (q.get("speed")) next.tick_delay = Number(q.get("speed"));
    setCfg(next);
    if (q.get("autorun") === "1") start(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);
  const roster = useMemo(() => new Map<string, AgentSpec>(derived.agents.map((a) => [a.spec.id, a.spec])), [derived.agents]);
  const running = !!runId && !derived.metrics && !derived.error;
  const set = (k: keyof RunConfig, v: any) => setCfg((c) => ({ ...c, [k]: v }));
  const err = derived.availability.length ? derived.services : null;
  const lastTel = [...messages].reverse().find((m) => m.type === "telemetry" && m.content.services && !m.content.event);

  return (
    <div className="h-full flex flex-col">
      <Header cfg={cfg} set={set} running={running} tab={tab} setTab={setTab}
        onRun={() => { setTab("live"); setSelected(null); start(cfg); }} onStop={stop}
        scenarios={meta?.scenarios ?? ["S1", "S2", "S3", "S5"]} modes={meta?.modes ?? ["A", "B", "C", "D"]}
        agentIds={derived.agents.map((a) => a.spec.id)} llmAvailable={!!meta?.llm?.available}
        llmModel={meta?.llm?.model} onHelp={() => setHelp(true)} />

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
