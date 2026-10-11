import { useEffect, useRef, useState } from "react";
import { MODES, SCENARIOS } from "../labels";
import type { RunConfig } from "../useRun";
import Info from "./Info";

interface Props {
  cfg: RunConfig;
  set: (k: keyof RunConfig, v: any) => void;
  running: boolean;
  onRun: () => void;
  onStop: () => void;
  tab: "live" | "results";
  setTab: (t: "live" | "results") => void;
  scenarios: string[];
  modes: string[];
  agentIds: string[];
  llmAvailable: boolean;
  llmModel?: string | null;
  onHelp: () => void;
}

export default function Header(p: Props) {
  const [open, setOpen] = useState(false);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const close = (e: MouseEvent) => {
      if (ref.current && !ref.current.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, []);
  const sc = SCENARIOS[p.cfg.scenario];
  const md = MODES[p.cfg.mode];

  return (
    <header className="border-b border-slate-800/80 bg-slate-950/90 px-6 py-4">
      <div className="flex flex-wrap items-center gap-x-8 gap-y-3">
        <div>
          <div className="text-xl font-black tracking-[0.18em] text-slate-50">GHOST PROTOCOL</div>
          <div className="text-sm text-slate-400">When AI agents disagree, who decides how to fix an outage?</div>
        </div>

        <nav className="flex gap-1 rounded-lg bg-slate-900 p-1 text-sm">
          {(["live", "results"] as const).map((t) => (
            <button key={t} onClick={() => p.setTab(t)}
              className={`rounded-md px-3 py-1 transition-colors ${p.tab === t ? "bg-slate-700 text-white" : "text-slate-400 hover:text-slate-200"}`}>
              {t === "live" ? "Live incident" : "Results"}
            </button>
          ))}
        </nav>

        {p.tab === "live" && (
          <div className="ml-auto flex flex-wrap items-start gap-4">
            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-slate-500">
                Incident<Info side="bottom" text="Which outage to simulate. Each one tests a different situation." />
              </span>
              <select value={p.cfg.scenario} disabled={p.running} onChange={(e) => p.set("scenario", e.target.value)}
                className="w-72 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-60">
                {p.scenarios.map((s) => <option key={s} value={s}>{SCENARIOS[s]?.name ?? s}</option>)}
              </select>
              <span className="w-72 text-xs leading-snug text-slate-400">{sc?.blurb}</span>
            </label>

            <label className="flex flex-col gap-1">
              <span className="text-[11px] uppercase tracking-wider text-slate-500">
                Who responds<Info side="bottom" text="How the outage is handled: a fixed rule (the baseline) or our AI agents." />
              </span>
              <select value={p.cfg.mode} disabled={p.running} onChange={(e) => p.set("mode", e.target.value)}
                className="w-72 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-sm text-slate-100 disabled:opacity-60">
                {p.modes.map((m) => <option key={m} value={m}>{MODES[m]?.name ?? m}</option>)}
              </select>
              <span className="w-72 text-xs leading-snug text-slate-400">{md?.blurb}</span>
            </label>

            <div className="flex items-center gap-2 pt-5">
              {p.running ? (
                <button onClick={p.onStop}
                  className="rounded-lg bg-slate-700 px-6 py-2.5 text-base font-semibold text-white hover:bg-slate-600">Stop</button>
              ) : (
                <button onClick={p.onRun}
                  className="rounded-lg bg-violet-600 px-6 py-2.5 text-base font-semibold text-white shadow-lg shadow-violet-900/40 hover:bg-violet-500">
                  Run incident
                </button>
              )}

              <div className="relative" ref={ref}>
                <button onClick={() => setOpen((o) => !o)} aria-expanded={open}
                  className={`rounded-lg border px-3 py-2.5 text-sm ${open ? "border-violet-500 text-violet-200" : "border-slate-700 text-slate-300 hover:border-slate-500"}`}>
                  Advanced ▾
                </button>
                {open && (
                  <div className="absolute right-0 top-12 z-40 w-80 space-y-4 rounded-xl border border-slate-700 bg-slate-900 p-4 shadow-2xl">
                    <Field label="Seed" help="The random seed. The same seed always replays the exact same incident.">
                      <input type="number" value={p.cfg.seed} onChange={(e) => p.set("seed", +e.target.value)}
                        className="w-24 rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm" />
                    </Field>
                    <Field label="Speed" help="How fast time passes in the simulation.">
                      <select value={p.cfg.tick_delay} onChange={(e) => p.set("tick_delay", +e.target.value)}
                        className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm">
                        <option value={1.5}>Slow</option><option value={0.8}>Demo</option>
                        <option value={0.25}>Fast</option><option value={0}>Instant</option>
                      </select>
                    </Field>
                    {p.cfg.mode === "D" && (
                      <Field label="Agents used after the rule" help="Which agent approach takes over when the fixed rule fails.">
                        <select value={p.cfg.agents_mode_for_d} onChange={(e) => p.set("agents_mode_for_d", e.target.value)}
                          className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm">
                          <option value="C">Negotiate</option><option value="B">Coordinator</option>
                        </select>
                      </Field>
                    )}
                    <Field label="Use the LLM" help={p.llmAvailable
                      ? `Agents read logs and phrase their messages with ${p.llmModel ?? "the LLM"}. Decisions are always made by code.`
                      : "No LLM key configured: agents use measured values and template sentences."}>
                      <input type="checkbox" disabled={!p.llmAvailable} checked={p.cfg.use_llm}
                        onChange={(e) => p.set("use_llm", e.target.checked)} className="h-4 w-4" />
                    </Field>
                    <Field label="Remove an agent's data" help="Ablation test: hide one agent's evidence to prove the outcome depends on what each agent sees.">
                      <select value={p.cfg.ablate ?? ""} onChange={(e) => p.set("ablate", e.target.value || null)}
                        className="rounded-md border border-slate-700 bg-slate-950 px-2 py-1 text-sm">
                        <option value="">None</option>
                        {p.agentIds.map((id) => <option key={id} value={id}>{id}</option>)}
                      </select>
                    </Field>
                  </div>
                )}
              </div>

              <button onClick={p.onHelp} title="How to read this page"
                className="h-10 w-10 rounded-full border border-slate-700 text-lg font-semibold text-slate-300 hover:border-violet-400 hover:text-violet-200">?</button>
            </div>
          </div>
        )}
      </div>
    </header>
  );
}

function Field({ label, help, children }: { label: string; help: string; children: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <span className="text-sm text-slate-300">{label}<Info text={help} /></span>
      {children}
    </div>
  );
}
