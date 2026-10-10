import { useEffect, useState } from "react";

// Shows eval/results/*.json files that have a "summary" list of rows:
// {scenario, mode, n, <metric>_mean, <metric>_lo, <metric>_hi}
const METRICS: { key: string; label: string; better: "high" | "low"; fmt: (v: number) => string }[] = [
  { key: "correct_diagnosis", label: "Correct diagnosis", better: "high", fmt: (v) => `${Math.round(v * 100)}%` },
  { key: "recovery_time", label: "Recovery time (ticks)", better: "low", fmt: (v) => v.toFixed(1) },
  { key: "availability", label: "Availability", better: "high", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  { key: "unnecessary_actions", label: "Unnecessary actions", better: "low", fmt: (v) => v.toFixed(2) },
  { key: "escalated_to_human", label: "Escalated to human", better: "high", fmt: (v) => `${Math.round(v * 100)}%` },
];
const MODE_COLOR: Record<string, string> = { A: "#64748b", B: "#3b82f6", C: "#a855f7", D: "#10b981" };
const MODE_NAME: Record<string, string> = { A: "Runbook", B: "Agents + aggregator", C: "Peer negotiation", D: "Hybrid" };

export default function Results() {
  const [data, setData] = useState<Record<string, any> | null>(null);
  const [file, setFile] = useState<string>("");
  useEffect(() => {
    fetch("/api/results").then((r) => r.json()).then((d) => {
      setData(d);
      setFile(Object.keys(d).find((k) => d[k]?.summary) ?? "");
    });
  }, []);
  if (!data) return <div className="p-6 text-slate-400">Loading…</div>;
  const rows: any[] = data[file]?.summary ?? [];
  if (!rows.length)
    return <div className="p-6 text-slate-400">No results yet. Run <span className="mono">uv run python eval/compare_modes.py</span>.</div>;
  const scenarios = [...new Set(rows.map((r) => r.scenario))];
  const modes = [...new Set(rows.map((r) => r.mode))].sort();
  return (
    <div className="p-4 space-y-4 overflow-y-auto h-full">
      <div className="flex items-center gap-3 text-sm">
        <span className="font-semibold">Results</span>
        <select value={file} onChange={(e) => setFile(e.target.value)} className="bg-slate-900 border border-slate-700 rounded px-2 py-1">
          {Object.keys(data).filter((k) => data[k]?.summary).map((k) => <option key={k}>{k}</option>)}
        </select>
        <span className="text-slate-500 text-xs">{data[file]?.note}</span>
        <div className="ml-auto flex gap-3">
          {modes.map((m) => (
            <span key={m} className="flex items-center gap-1 text-xs"><span className="h-2.5 w-2.5 rounded-sm" style={{ background: MODE_COLOR[m] }} />{m}: {MODE_NAME[m]}</span>
          ))}
        </div>
      </div>
      <div className="grid grid-cols-1 lg:grid-cols-2 2xl:grid-cols-3 gap-4">
        {METRICS.map((met) => {
          const max = Math.max(...rows.map((r) => r[`${met.key}_hi`] ?? r[`${met.key}_mean`] ?? 0), met.key === "recovery_time" ? 1 : 1);
          return (
            <div key={met.key} className="rounded-lg border border-slate-800 bg-slate-900/60 p-3">
              <div className="text-sm font-semibold mb-2">{met.label} <span className="text-xs text-slate-500">({met.better} is better)</span></div>
              <div className="space-y-3">
                {scenarios.map((s) => (
                  <div key={s}>
                    <div className="text-xs text-slate-400 mb-1">{s}</div>
                    {modes.map((m) => {
                      const r = rows.find((x) => x.scenario === s && x.mode === m);
                      if (!r) return null;
                      const v = r[`${met.key}_mean`] ?? 0, lo = r[`${met.key}_lo`], hi = r[`${met.key}_hi`];
                      return (
                        <div key={m} className="flex items-center gap-2 h-4">
                          <span className="w-4 text-[10px] mono text-slate-500">{m}</span>
                          <div className="relative flex-1 h-3 bg-slate-800 rounded">
                            <div className="h-3 rounded" style={{ width: `${(v / max) * 100}%`, background: MODE_COLOR[m] }} />
                            {lo != null && hi != null && (
                              <div className="absolute top-1/2 h-px bg-slate-200" style={{ left: `${(lo / max) * 100}%`, width: `${((hi - lo) / max) * 100}%` }} />
                            )}
                          </div>
                          <span className="w-12 text-right text-[10px] mono">{met.fmt(v)}</span>
                        </div>
                      );
                    })}
                  </div>
                ))}
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
