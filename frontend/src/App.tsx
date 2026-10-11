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
import { act, hyp } from "./labels";
import type { AgentSpec, Msg } from "./types";
import { useRun, type RunConfig } from "./useRun";

function Step({ n, title, help, children, className = "", right, collapsible, open = true, onToggle, summary }: {
  n: number; title: string; help: string; children: React.ReactNode; className?: string; right?: React.ReactNode;
  collapsible?: boolean; open?: boolean; onToggle?: () => void; summary?: React.ReactNode;
}) {
  const head = (
    <div className="flex w-full items-center gap-3 text-left">
      <span className="flex h-8 w-8 shrink-0 items-center justify-center rounded-full bg-violet-600/20 text-sm font-bold text-violet-300">{n}</span>
      <div className="min-w-0 flex-1">
        <h2 className="text-xl font-semibold leading-tight text-slate-50">{title}</h2>
        {collapsible && !open
          ? <div className="mt-0.5 truncate text-[15px] text-slate-300">{summary}</div>
          : <p className="text-sm text-slate-400">{help}</p>}
      </div>
      {right && <div className="shrink-0">{right}</div>}
      {collapsible && (
        <span className={`flex shrink-0 items-center gap-1.5 rounded-full border px-3 py-1 text-sm transition-colors ${open ? "border-violet-500/60 text-violet-200" : "border-slate-700 text-slate-300"}`}>
          {open ? "Hide" : "Show"} <span className={`transition-transform duration-300 ${open ? "rotate-180" : ""}`}>▾</span>
        </span>
      )}
    </div>
  );
  return (
    <section className={`flex min-h-0 flex-col rounded-2xl border border-slate-800/80 bg-slate-950/60 p-5 shadow-[0_1px_0_rgba(255,255,255,0.03)_inset] ${className}`}>
      {collapsible
        ? <button onClick={onToggle} aria-expanded={open} className="rounded-xl outline-none focus-visible:ring-2 focus-visible:ring-violet-500">{head}</button>
        : head}
      {(!collapsible || open) && <div className="mt-4 flex min-h-0 flex-1 flex-col">{children}</div>}
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
    agents_mode_for_d: "C", escalate_on_conflict: true, ablate: null,
  });
  const [selected, setSelected] = useState<Msg | null>(null);
  const [agentFilter, setAgentFilter] = useState<string | null>(null);
  const [fullLedger, setFullLedger] = useState(false);
  const [help, setHelp] = useState(false);
  const [official, setOfficial] = useState<any[] | null>(null);
  const [showAgents, setShowAgents] = useState(false);
  const [showOutcome, setShowOutcome] = useState(false);
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
    const opened = (q.get("open") ?? "").split(",");
    if (opened.includes("2")) setShowAgents(true);
    if (opened.includes("4")) setShowOutcome(true);
    setCfg(next);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const phase = derived.mode?.mode ?? (runId ? "monitoring" : "idle");
  const ph = PHASE[phase] ?? PHASE.idle;
  const openById = (id: number) => setSelected(derived.byId.get(id) ?? null);
  const run = derived.start?.content;

  const thinking = derived.agents.filter((a) => a.belief);
  const votes = new Map<string, number>();
  for (const a of thinking) {
    const top = Object.entries(a.belief!).sort((x, y) => y[1] - x[1])[0][0];
    votes.set(top, (votes.get(top) ?? 0) + 1);
  }
  const lead = [...votes.entries()].sort((x, y) => y[1] - x[1])[0];
  const agentsSummary = lead
    ? <span>{lead[1]} of {thinking.length} agents think it's <b className="text-white">{hyp(lead[0])}</b>{votes.size > 1 ? <span className="text-slate-400"> · {votes.size - 1} other view{votes.size > 2 ? "s" : ""}</span> : null}</span>
    : <span className="text-slate-400">{derived.agents.length} AI agents standing by, each watching a different part of the system</span>;
  const decision = [...messages].reverse().find((m) => m.type === "action" && m.content.action !== "probe");
  const mt = derived.metrics;
  const outcomeSummary = mt
    ? <span><b className={mt.recovery_time < 30 ? "text-emerald-300" : "text-red-300"}>{mt.recovery_time < 30 ? `Recovered in ${mt.recovery_time} min` : "Did not recover"}</b>
        <span className="text-slate-400"> · {mt.unnecessary_actions} wrong fix{mt.unnecessary_actions === 1 ? "" : "es"} · {mt.escalated_to_human ? "asked a human" : "no human needed"}{decision ? ` · ${act(decision.content.action).toLowerCase()}` : ""}</span></span>
    : decision ? <span>Decision so far: <b className="text-white">{act(decision.content.action)}</b></span>
      : <span className="text-slate-400">The decision and the scorecard appear here when the incident ends</span>;

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
            {derived.mode?.reason && phase !== "idle" && <span className="max-w-xl truncate text-sm text-slate-400" title={derived.mode.reason}>
              {phase === "resolved" ? `All services healthy again at minute ${derived.mode.tick}.` : derived.mode.reason}</span>}
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

          <div className="grid gap-5 xl:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
            <div className="flex min-w-0 flex-col gap-5">
              <Step n={1} title="What broke" help="The payments platform. Failing services glow red; hover a service for all of its numbers.">
                <ServiceGraph services={derived.services} />
              </Step>
              <Step n={2} title="What the agents think" collapsible open={showAgents} onToggle={() => setShowAgents((o) => !o)} summary={agentsSummary}
                help="Each agent sees only its own data and guesses the cause. Their goals differ, so they can disagree.">
                <AgentRoster agents={derived.agents} cids={derived.agntcy?.cids}
                  onSelect={(id) => { setAgentFilter(id); setFullLedger(true); }} />
              </Step>
            </div>

            <div className="flex min-w-0 flex-col gap-5 xl:h-[calc(100vh-200px)] xl:min-h-[700px]">
              <Step n={3} title="How they decided" className="min-h-[420px] flex-1"
                help={fullLedger ? "Every message, including each vote. Click a line for details." : "The key moments, in order. Click any moment to see the evidence behind it."}
                right={<span onClick={(e) => { e.stopPropagation(); setFullLedger((f) => !f); }} role="button" tabIndex={0}
                  className="cursor-pointer rounded-full border border-slate-700 px-3 py-1 text-xs text-slate-400 hover:border-slate-500 hover:text-slate-200">
                  {fullLedger ? "Back to the story" : "Full log"}</span>}>
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
              <Step n={4} title="Did it work" collapsible open={showOutcome} onToggle={() => setShowOutcome((o) => !o)} summary={outcomeSummary}
                className="shrink-0" help="What was done, and how the outcome compares with the fixed-rule baseline.">
                <div className="space-y-3 overflow-y-auto">
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
