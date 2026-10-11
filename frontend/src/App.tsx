import { useEffect, useMemo, useRef, useState } from "react";
import AgentRoster from "./components/AgentRoster";
import ApprovalPanel from "./components/ApprovalPanel";
import DetailDrawer from "./components/DetailDrawer";
import Header from "./components/Header";
import HowTo, { seenHowTo } from "./components/HowTo";
import Info from "./components/Info";
import Ledger from "./components/Ledger";
import { DecisionCard, ResultCard } from "./components/Outcome";
import Results from "./components/Results";
import ServiceGraph from "./components/ServiceGraph";
import Timeline from "./components/Timeline";
import type { AgentSpec, Msg } from "./types";
import { useRun, type RunConfig } from "./useRun";

function Step({ n, title, help, children, className = "", right }: {
  n: number; title: string; help: string; children: React.ReactNode; className?: string; right?: React.ReactNode;
}) {
  return (
    <section className={`flex min-h-0 flex-col rounded-2xl border border-slate-800/80 bg-slate-950/60 p-4 ${className}`}>
      <div className="mb-3 flex items-start gap-3">
        <span className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full bg-violet-600/20 text-sm font-bold text-violet-300">{n}</span>
        <div className="min-w-0">
          <h2 className="text-lg font-semibold leading-tight text-slate-50">{title}</h2>
          <p className="text-sm text-slate-400">{help}</p>
        </div>
        {right && <div className="ml-auto shrink-0">{right}</div>}
      </div>
      {children}
    </section>
  );
}

const PHASE: Record<string, { label: string; cls: string }> = {
  idle: { label: "Ready: pick an incident and press Run", cls: "bg-slate-800 text-slate-300" },
  monitoring: { label: "Watching the system", cls: "bg-slate-800 text-slate-200" },
  runbook: { label: "The fixed rule is handling it", cls: "bg-slate-700 text-white" },
  agents: { label: "The AI agents are handling it", cls: "bg-violet-600/30 text-violet-100" },
  resolved: { label: "Resolved", cls: "bg-emerald-600/25 text-emerald-200" },
};

export default function App() {
  const { runId, messages, derived, meta, connected, start, stop, answer } = useRun();
  const [tab, setTab] = useState<"live" | "results">("live");
  const [cfg, setCfg] = useState<RunConfig>({
    scenario: "S2", mode: "D", seed: 2, use_llm: false, tick_delay: 0.8,
    agents_mode_for_d: "C", escalate_on_conflict: false, ablate: null,
  });
  const [selected, setSelected] = useState<Msg | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const [fullLedger, setFullLedger] = useState(false);
  const [help, setHelp] = useState(false);
  const [official, setOfficial] = useState<any[] | null>(null);
  const roster = useMemo(() => new Map<string, AgentSpec>(derived.agents.map((a) => [a.spec.id, a.spec])), [derived.agents]);
  const running = !!runId && !derived.metrics && !derived.error;
  const set = (k: keyof RunConfig, v: any) => setCfg((c) => ({ ...c, [k]: v }));
  const lastTel = [...messages].reverse().find((m) => m.type === "telemetry" && m.content.services && !m.content.event);
  const started = useRef(false);

  useEffect(() => {
    const q = new URLSearchParams(location.search);
    if (!seenHowTo() && !q.get("autorun") && !q.get("tab")) setHelp(true);
    fetch("/api/results").then((r) => r.json()).then((d) => setOfficial(d.official?.summary ?? null)).catch(() => {});
  }, []);

  // Shareable demo links: ?scenario=S5&mode=C&seed=1&speed=0&autorun=1
  useEffect(() => {
    if (started.current) return;
    started.current = true;
    const q = new URLSearchParams(location.search);
    const next = { ...cfg };
    if (q.get("scenario")) next.scenario = q.get("scenario")!;
    if (q.get("mode")) next.mode = q.get("mode")!;
    if (q.get("seed")) next.seed = Number(q.get("seed"));
    if (q.get("speed")) next.tick_delay = Number(q.get("speed"));
    if (q.get("autorun") === "1") { setHelp(false); start(next); }
    if (q.get("tab") === "results") { setHelp(false); setTab("results"); }
    setCfg(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const phase = derived.mode?.mode ?? (runId ? "monitoring" : "idle");
  const ph = PHASE[phase] ?? PHASE.idle;
  const openById = (id: number) => setSelected(derived.byId.get(id) ?? null);
  const run = derived.start?.content;

  return (
    <div className="flex min-h-full flex-col bg-[radial-gradient(ellipse_at_top,_rgba(91,33,182,0.10),_transparent_55%)]">
      <Header cfg={cfg} set={set} running={running} tab={tab} setTab={setTab}
        onRun={() => { setTab("live"); setSelected(null); setFullLedger(false); start(cfg); }} onStop={stop}
        scenarios={meta?.scenarios ?? ["S1", "S2", "S3", "S5"]} modes={meta?.modes ?? ["A", "B", "C", "D"]}
        agentIds={derived.agents.map((a) => a.spec.id)} llmAvailable={!!meta?.llm?.available}
        llmModel={meta?.llm?.model} onHelp={() => setHelp(true)} />

      {meta?.error && <div className="bg-red-900/50 px-6 py-1 text-sm text-red-200">Backend not reachable. Start it: <code>uv run uvicorn backend.main:app --port 8000</code></div>}

      {tab === "results" ? <Results /> : (
        <main className="flex-1 space-y-4 px-6 py-4">
          {/* status strip */}
          <div className="flex flex-wrap items-center gap-4">
            <span className={`rounded-full px-4 py-1.5 text-sm font-semibold transition-colors duration-500 ${ph.cls}`}>{ph.label}</span>
            {derived.mode?.reason && phase !== "idle" && <span className="max-w-xl truncate text-sm text-slate-400" title={derived.mode.reason}>{derived.mode.reason}</span>}
            <div className="ml-auto flex items-center gap-5 text-sm text-slate-400">
              <div className="flex items-center gap-2">
                <span>Minute {derived.tick} of 30<Info text="The simulation runs 30 ticks (think: minutes). The fault starts at minute 5." /></span>
                <div className="h-1.5 w-32 overflow-hidden rounded-full bg-slate-800">
                  <div className="h-full rounded-full bg-violet-500 transition-all duration-500" style={{ width: `${(derived.tick / 30) * 100}%` }} />
                </div>
              </div>
              {lastTel && <span>Errors <b className={lastTel.content.error_rate > 0.03 ? "text-red-300" : "text-emerald-300"}>{(lastTel.content.error_rate * 100).toFixed(1)}%</b></span>}
              {lastTel && <span>Latency <b className={lastTel.content.latency_ms > 300 ? "text-red-300" : "text-emerald-300"}>{Math.round(lastTel.content.latency_ms)} ms</b></span>}
              {lastTel?.content.lockout > 0 && <span className="font-semibold text-amber-300">Customers locked out!</span>}
              {derived.agntcy?.enabled && <span className={derived.agntcy.directory === "ok" ? "text-emerald-400" : "text-amber-400"}>AGNTCY {derived.agntcy.directory === "ok" ? "on" : "fallback"}<Info text="Agents are registered in the AGNTCY Directory and every message is traced with OpenTelemetry." /></span>}
              <span className={connected ? "text-emerald-400" : "text-slate-600"}>● {connected ? "live" : "idle"}</span>
            </div>
          </div>
          {derived.error && <div className="rounded-lg border border-red-600 bg-red-950 p-2 text-sm text-red-200">{derived.error}</div>}

          <div className="grid gap-4 xl:grid-cols-[minmax(0,1.15fr)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-4">
              <Step n={1} title="What broke" help="The payments platform. Failing services glow red; hover a service for all its numbers.">
                <ServiceGraph services={derived.services} />
              </Step>
              <Step n={2} title="What the agents think" help="Each agent sees only its own data and guesses the cause. Their goals differ, so they can disagree.">
                <AgentRoster agents={derived.agents} cids={derived.agntcy?.cids}
                  onSelect={(id) => { setAgentFilter(id); setFullLedger(true); }} />
              </Step>
            </div>

            <div className="flex min-w-0 flex-col gap-4 xl:h-[calc(100vh-200px)] xl:min-h-[760px]">
              <Step n={3} title="How they decided" className="min-h-[380px] flex-1"
                help={fullLedger ? "Every message, including votes. Click any line for details." : "The key moments: claims, challenges, changes of mind, and the decision. Click any moment for details."}
                right={<button onClick={() => setFullLedger((f) => !f)}
                  className="rounded-lg border border-slate-700 px-2.5 py-1 text-xs text-slate-300 hover:border-slate-500">
                  {fullLedger ? "Back to key moments" : "Show full ledger"}</button>}>
                <div className="min-h-0 flex-1">
                  {fullLedger ? (
                    <div className="h-full overflow-hidden rounded-lg border border-slate-800">
                      <Ledger messages={messages} roster={roster} selected={selected?.id ?? null} onSelect={setSelected}
                        agentFilter={agentFilter} clearAgentFilter={() => setAgentFilter(null)} traceId={derived.agntcy?.trace_id} />
                    </div>
                  ) : (
                    <Timeline messages={messages} roster={roster} onSelect={openById} />
                  )}
                </div>
              </Step>
              <Step n={4} title="Did it work" help="What was done, and how the outcome compares with the fixed-rule baseline.">
                <div className="space-y-3">
                  <DecisionCard messages={messages} roster={roster} onOpen={setSelected} />
                  <ResultCard metrics={derived.metrics} scenario={run?.scenario ?? cfg.scenario} mode={run?.mode ?? cfg.mode} official={official} />
                </div>
              </Step>
            </div>
          </div>
        </main>
      )}

      {selected && <DetailDrawer msg={selected} byId={derived.byId} roster={roster} onClose={() => setSelected(null)} onSelect={setSelected} />}
      {derived.escalation && (
        <ApprovalPanel key={derived.escalation.id} esc={derived.escalation} onAnswer={answer}
          onShowProvenance={() => setSelected(derived.escalation)} />
      )}
      {help && <HowTo onClose={() => setHelp(false)} />}
    </div>
  );
}
