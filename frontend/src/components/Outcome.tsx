import { act, MODES, SENDER_NAME } from "../labels";
import type { AgentSpec, Metrics, Msg } from "../types";
import Info from "./Info";

// "Did it work": the decision that was taken, the headline numbers, and how this
// approach compares with the fixed-rule baseline over the official evaluation runs.

function plainRisk(rationale: string): string {
  const m = rationale.match(/Validator:\s*(.+?)\.?$/);
  if (!m) return "";
  return m[1] === "safe" ? "Safety check: no known risk." : `Safety check: ${m[1]}.`;
}

export function DecisionCard({ messages, roster, onOpen }: {
  messages: Msg[]; roster: Map<string, AgentSpec>; onOpen: (m: Msg) => void;
}) {
  const decision = [...messages].reverse().find((m) => m.type === "action" && m.content.action !== "probe");
  if (!decision) return null;
  const who = roster.get(decision.sender)?.name ?? SENDER_NAME[decision.sender] ?? decision.sender;
  const agreed = decision.rationale.match(/(\d+)\/(\d+) accepted/);
  const vetoes = messages.filter((m) => m.type === "veto" && m.id < decision.id);
  const human = decision.sender === "human";
  const notes: string[] = [];
  if (agreed) notes.push(`${agreed[1]} of ${agreed[2]} agents agreed`);
  if (vetoes.length) notes.push(`${vetoes.length} veto${vetoes.length > 1 ? "es" : ""} along the way`);
  if (human) notes.push("approved by a human");
  if (decision.sender === "runbook") notes.push("no discussion: a fixed rule fired");
  return (
    <button onClick={() => onOpen(decision)}
      className="block w-full rounded-xl border border-slate-700 bg-slate-900/70 px-4 py-3 text-left transition-colors hover:border-slate-500">
      <div className="flex items-baseline gap-3">
        <span className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">Decision · minute {decision.tick}</span>
        <span className="ml-auto text-xs text-violet-300">Why? See the evidence trail →</span>
      </div>
      <div className="text-xl font-semibold text-white">{act(decision.content.action)}</div>
      <div className="text-sm text-slate-300">Proposed by <b>{who}</b>{notes.length ? ` · ${notes.join(" · ")}` : ""}</div>
      <div className="text-sm text-slate-400">{plainRisk(decision.rationale)}</div>
    </button>
  );
}

const TILE_HELP = {
  recovery: "Minutes (simulation ticks) from the fault starting until the system stayed healthy for 3 ticks. Lower is better.",
  availability: "Share of customer requests that succeeded during the run, counting customers wrongly locked out as failures.",
  unnecessary: "Fixes that were applied but weren't needed. Each one can cause harm.",
  human: "Whether the team stopped and asked a person because acting alone was too risky.",
};

function Tile({ label, value, help, good }: { label: string; value: string; help: string; good: boolean | null }) {
  return (
    <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-3 py-2">
      <div className="text-[11px] uppercase tracking-wider text-slate-400">{label}<Info text={help} /></div>
      <div className={`text-2xl font-semibold tabular-nums ${good === null ? "text-white" : good ? "text-emerald-300" : "text-red-300"}`}>{value}</div>
    </div>
  );
}

export function ResultCard({ metrics, scenario, mode, official }: {
  metrics: Metrics | null; scenario?: string; mode?: string; official: any[] | null;
}) {
  const row = (m: string) => official?.find((r) => r.scenario === scenario && r.mode === m);
  const cols = [
    { m: "A", label: "Fixed rule", r: row("A") },
    { m: "C", label: "Our agents", r: row("C") },
    ...(mode && mode !== "A" && mode !== "C" ? [{ m: mode, label: MODES[mode]?.name ?? mode, r: row(mode) }] : []),
  ].filter((c) => c.r);
  return (
    <div className="space-y-2.5">
      {metrics ? (
        <div className="grid grid-cols-4 gap-2">
          <Tile label="Recovery" value={`${metrics.recovery_time} min`} help={TILE_HELP.recovery} good={metrics.recovery_time < 15} />
          <Tile label="Availability" value={`${(metrics.availability * 100).toFixed(1)}%`} help={TILE_HELP.availability} good={metrics.availability >= 0.95} />
          <Tile label="Wrong fixes" value={String(metrics.unnecessary_actions)} help={TILE_HELP.unnecessary} good={metrics.unnecessary_actions === 0} />
          <Tile label="Asked a human" value={metrics.escalated_to_human ? "Yes" : "No"} help={TILE_HELP.human} good={null} />
        </div>
      ) : (
        <div className="rounded-xl border border-dashed border-slate-800 p-3 text-sm text-slate-500">The numbers appear when the incident ends.</div>
      )}
      {cols.length >= 2 && (
        <div className="rounded-xl border border-slate-800 bg-slate-900/40 px-3 py-2">
          <div className="text-xs text-slate-400">The same incident over {cols[0].r.n} simulated runs<Info text="From the official evaluation (eval/results/official.json): every approach faced the same 100 seeded incidents." /></div>
          <table className="mt-1 w-full text-sm">
            <thead><tr className="text-left text-xs text-slate-500"><th className="font-normal" />
              {cols.map((c) => <th key={c.m} className={`font-normal ${c.m === "C" ? "text-violet-300" : ""}`}>{c.label}</th>)}</tr></thead>
            <tbody className="tabular-nums">
              <Row label="Right fix first" cells={cols.map((c) => `${Math.round(c.r.correct_diagnosis_mean * 100)}%`)} />
              <Row label="Recovery" cells={cols.map((c) => `${c.r.recovery_time_mean.toFixed(1)} min`)} />
              <Row label="Wrong fixes per run" cells={cols.map((c) => c.r.unnecessary_actions_mean.toFixed(2))} />
              <Row label="Asked a human" cells={cols.map((c) => `${Math.round(c.r.escalated_to_human_mean * 100)}%`)} />
            </tbody>
          </table>
        </div>
      )}
    </div>
  );
}

function Row({ label, cells }: { label: string; cells: string[] }) {
  return <tr className="border-t border-slate-800/80"><td className="py-0.5 text-slate-400">{label}</td>
    {cells.map((c, i) => <td key={i} className={i === 1 ? "font-semibold text-white" : "text-slate-300"}>{c}</td>)}</tr>;
}
