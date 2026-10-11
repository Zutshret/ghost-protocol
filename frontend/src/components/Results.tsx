import { useEffect, useMemo, useState } from "react";
import { MODES } from "../labels";
import Info from "./Info";

// Results: one comparison (fixed rule vs our agents) up front, details collapsed.
// Palette validated with the dataviz checks on the dark surface: cyan-600 / violet-500.
const SERIES = [
  { mode: "A", label: "Fixed rule (baseline)", color: "#0891b2" },
  { mode: "C", label: "Our agents (negotiate)", color: "#8b5cf6" },
];

const SHORT: Record<string, string> = {
  S1: "Clear database failure",
  S2: "Release disguised as attack",
  S3: "Slow dependency",
  S5: "Ambiguous and risky",
};

type Row = Record<string, any>;

const PANELS: { key: string; title: string; sub: string; value: (r: Row) => number; lo: (r: Row) => number; hi: (r: Row) => number; fmt: (v: number) => string }[] = [
  { key: "recovery", title: "Time to recover", sub: "minutes, lower is better", value: (r) => r.recovery_time_mean,
    lo: (r) => r.recovery_time_lo, hi: (r) => r.recovery_time_hi, fmt: (v) => `${v.toFixed(1)}` },
  { key: "failed", title: "Failed customer requests", sub: "100% − availability, lower is better", value: (r) => (1 - r.availability_mean) * 100,
    lo: (r) => (1 - r.availability_hi) * 100, hi: (r) => (1 - r.availability_lo) * 100, fmt: (v) => `${v.toFixed(1)}%` },
  { key: "wrong", title: "Wrong fixes per incident", sub: "unneeded actions, lower is better", value: (r) => r.unnecessary_actions_mean,
    lo: (r) => r.unnecessary_actions_lo, hi: (r) => r.unnecessary_actions_hi, fmt: (v) => v.toFixed(2) },
];

function takeaway(rows: Row[]): string {
  const get = (s: string, m: string) => rows.find((r) => r.scenario === s && r.mode === m);
  const hard = ["S2", "S5"].map((s) => [get(s, "A"), get(s, "C")]).filter(([a, c]) => a && c) as Row[][];
  const s1a = get("S1", "A"), s1c = get("S1", "C");
  if (!hard.length) return "";
  const avg = (xs: number[]) => xs.reduce((a, b) => a + b, 0) / xs.length;
  const ruleRight = Math.round(avg(hard.map(([a]) => a.correct_diagnosis_mean)) * 100);
  const agentRight = Math.round(avg(hard.map(([, c]) => c.correct_diagnosis_mean)) * 100);
  const tie = s1a && s1c && Math.abs(s1a.correct_diagnosis_mean - s1c.correct_diagnosis_mean) < 0.03;
  return `${tie ? "On the clear-cut failure both approaches do equally well. " : ""}When the evidence is misleading or risky, our agents choose the right fix ${agentRight}% of the time versus ${ruleRight}% for the fixed rule, and they ask a human instead of guessing when every fix is risky.`;
}

function Panel({ rows, scenarios, p, hover, setHover }: {
  rows: Row[]; scenarios: string[]; p: (typeof PANELS)[number];
  hover: string | null; setHover: (k: string | null) => void;
}) {
  const max = Math.max(...rows.filter((r) => SERIES.some((s) => s.mode === r.mode)).map((r) => p.hi(r) ?? p.value(r)), 0.0001) * 1.12;
  return (
    <figure className="rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
      <figcaption className="mb-3">
        <div className="text-base font-semibold text-slate-100">{p.title}</div>
        <div className="text-xs text-slate-400">{p.sub}</div>
      </figcaption>
      <div className="space-y-4">
        {scenarios.map((sc) => (
          <div key={sc}>
            <div className="mb-1 text-xs text-slate-400">{SHORT[sc] ?? sc}</div>
            <div className="space-y-[2px]">
              {SERIES.map((s) => {
                const r = rows.find((x) => x.scenario === sc && x.mode === s.mode);
                if (!r) return null;
                const v = p.value(r);
                const id = `${p.key}-${sc}-${s.mode}`;
                return (
                  <div key={s.mode} className="relative flex h-5 items-center gap-2"
                    onMouseEnter={() => setHover(id)} onMouseLeave={() => setHover(null)}>
                    <div className="relative h-3 flex-1">
                      <div className="absolute inset-y-0 left-0 rounded-r-[4px] transition-all duration-500"
                        style={{ width: `${Math.max(0.6, (v / max) * 100)}%`, background: s.color, opacity: hover && hover !== id ? 0.45 : 1 }} />
                    </div>
                    <span className="w-14 text-right text-xs tabular-nums text-slate-200">{p.fmt(v)}</span>
                    {hover === id && (
                      <div className="pointer-events-none absolute -top-14 left-1/3 z-20 w-64 rounded-lg border border-slate-700 bg-slate-900 px-3 py-2 text-xs shadow-xl">
                        <div className="font-semibold text-slate-100">{s.label}</div>
                        <div className="text-slate-300">{SHORT[sc]}: <b>{p.fmt(v)}</b> <span className="text-slate-500">(95% CI {p.fmt(p.lo(r))}–{p.fmt(p.hi(r))}, {r.n} runs)</span></div>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          </div>
        ))}
      </div>
    </figure>
  );
}

const pct = (v?: number) => (v == null ? "-" : `${Math.round(v * 100)}%`);

export default function Results() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [file, setFile] = useState("");
  const [hover, setHover] = useState<string | null>(null);
  useEffect(() => {
    fetch("/api/results").then((r) => r.json()).then((d) => {
      setData(d);
      setFile(d.official?.summary ? "official" : Object.keys(d).find((k) => d[k]?.summary) ?? "");
    });
  }, []);
  const rows: Row[] = data?.[file]?.summary ?? [];
  const scenarios = useMemo(() => [...new Set(rows.map((r) => r.scenario))].sort(), [rows]);
  const modes = useMemo(() => [...new Set(rows.map((r) => r.mode))].sort(), [rows]);
  if (!data) return <div className="p-8 text-slate-400">Loading…</div>;
  if (!rows.length) return <div className="p-8 text-slate-400">No results yet. Run <code>uv run python eval/evaluate.py</code>.</div>;

  return (
    <main className="mx-auto w-full max-w-[1500px] space-y-6 px-6 py-6">
      <div>
        <h1 className="text-2xl font-semibold text-white">Does it work? Fixed rule vs our agents</h1>
        <p className="mt-2 max-w-4xl text-lg leading-relaxed text-slate-300">{takeaway(rows)}</p>
        <p className="mt-1 text-sm text-slate-500">{data[file]?.note}</p>
      </div>

      <div className="flex flex-wrap items-center gap-5 text-sm">
        {SERIES.map((s) => (
          <span key={s.mode} className="flex items-center gap-2 text-slate-200">
            <span className="h-3 w-3 rounded-sm" style={{ background: s.color }} />{s.label}
          </span>
        ))}
        <span className="text-slate-500">Hover a bar for its 95% confidence interval.</span>
      </div>

      <div className="grid gap-4 lg:grid-cols-3">
        {PANELS.map((p) => <Panel key={p.key} rows={rows} scenarios={scenarios} p={p} hover={hover} setHover={setHover} />)}
      </div>

      <details className="group rounded-2xl border border-slate-800 bg-slate-950/60 p-4">
        <summary className="cursor-pointer select-none text-base font-semibold text-slate-200">
          Per-scenario detail: all four approaches <span className="text-sm font-normal text-slate-500 group-open:hidden">(click to expand)</span>
        </summary>
        <div className="mt-4 flex items-center gap-3 text-sm text-slate-400">
          Results file
          <select value={file} onChange={(e) => setFile(e.target.value)} className="rounded-md border border-slate-700 bg-slate-900 px-2 py-1 text-slate-200">
            {Object.keys(data).filter((k) => data[k]?.summary).map((k) => <option key={k}>{k}</option>)}
          </select>
        </div>
        <div className="mt-4 space-y-6">
          {scenarios.map((sc) => (
            <div key={sc}>
              <div className="mb-2 font-medium text-slate-200">{SHORT[sc] ?? sc} <span className="text-xs text-slate-500">({sc})</span></div>
              <table className="w-full text-sm">
                <thead>
                  <tr className="text-left text-xs text-slate-500">
                    <th className="py-1 font-normal">Approach</th>
                    <th className="font-normal">Right fix first<Info text="The first real action taken was the correct fix." /></th>
                    <th className="font-normal">Recovery (min)</th>
                    <th className="font-normal">Availability</th>
                    <th className="font-normal">Wrong fixes</th>
                    <th className="font-normal">Asked a human</th>
                  </tr>
                </thead>
                <tbody className="tabular-nums">
                  {modes.map((m) => {
                    const r = rows.find((x) => x.scenario === sc && x.mode === m);
                    if (!r) return null;
                    return (
                      <tr key={m} className={`border-t border-slate-800/80 ${m === "C" ? "text-white" : "text-slate-300"}`}>
                        <td className="py-1.5">{MODES[m]?.name ?? m}</td>
                        <td>{pct(r.correct_diagnosis_mean)}</td>
                        <td>{r.recovery_time_mean?.toFixed(1)}</td>
                        <td>{(r.availability_mean * 100).toFixed(1)}%</td>
                        <td>{r.unnecessary_actions_mean?.toFixed(2)}</td>
                        <td>{pct(r.escalated_to_human_mean)}</td>
                      </tr>
                    );
                  })}
                </tbody>
              </table>
            </div>
          ))}
        </div>
      </details>
    </main>
  );
}
