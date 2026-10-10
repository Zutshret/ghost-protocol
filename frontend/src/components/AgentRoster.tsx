import { HYPOTHESES, HYP_COLOR } from "../types";
import { pct, type AgentView } from "../useRun";

const SHORT: Record<string, string> = {
  bad_deploy: "deploy",
  attack: "attack",
  db_fault: "db",
  dependency_timeout: "dep. timeout",
};

function BeliefBars({ belief, prev }: { belief?: Record<string, number>; prev?: Record<string, number> }) {
  return (
    <div className="space-y-1">
      {HYPOTHESES.map((h) => {
        const p = belief?.[h] ?? 0.25;
        const d = prev ? p - (prev[h] ?? 0) : 0;
        return (
          <div key={h} className="flex items-center gap-2 text-[10px]">
            <span className="w-16 text-slate-400 truncate">{SHORT[h]}</span>
            <div className="flex-1 h-2 rounded bg-slate-800 overflow-hidden">
              <div className="h-full rounded transition-all duration-700 ease-out"
                style={{ width: `${p * 100}%`, background: HYP_COLOR[h], opacity: belief ? 1 : 0.25 }} />
            </div>
            <span className="w-8 text-right mono text-slate-300">{belief ? pct(p) : ""}</span>
            <span className={`w-6 text-right mono ${d > 0.05 ? "text-emerald-400" : d < -0.05 ? "text-red-400" : "text-transparent"}`}>
              {d > 0.05 ? "▲" : d < -0.05 ? "▼" : "·"}
            </span>
          </div>
        );
      })}
    </div>
  );
}

export default function AgentRoster({ agents, onSelect, cids }: {
  agents: AgentView[]; onSelect: (id: string) => void; cids?: Record<string, string>;
}) {
  return (
    <div className="grid grid-cols-2 xl:grid-cols-3 gap-3">
      {agents.map((a) => {
        const s = a.spec;
        const vetoing = a.lastType === "veto";
        return (
          <button key={s.id} onClick={() => onSelect(s.id)}
            className={`text-left rounded-lg border bg-slate-900/80 p-3 transition-all duration-300 hover:bg-slate-900
              ${a.active ? "opacity-100" : "opacity-40"} ${vetoing ? "border-orange-500" : "border-slate-800"}
              ${a.recruitedMidIncident ? "ring-2 ring-cyan-400/60" : ""}`}
            style={{ borderLeft: `4px solid ${s.color}` }}>
            <div className="flex items-center gap-2">
              <span className="font-semibold text-sm" style={{ color: s.color }}>{s.name}</span>
              {s.safety_critical && <span className="text-[9px] px-1 rounded bg-orange-500/20 text-orange-300">VETO</span>}
              {!s.core && <span className="text-[9px] px-1 rounded bg-cyan-500/20 text-cyan-300">SPECIALIST</span>}
              <span className="ml-auto text-[10px] text-slate-500">{a.active ? "active" : s.core ? "idle" : "on registry"}</span>
            </div>
            {cids?.[s.id] && (
              <div className="mt-1 text-[10px] mono text-emerald-300/90 truncate" title={`AGNTCY Directory record (CID): ${cids[s.id]}`}>
                <span className="px-1 rounded bg-emerald-500/15 mr-1">AGNTCY ✓</span>registered · {cids[s.id].slice(0, 10)}…{cids[s.id].slice(-6)}
              </div>
            )}
            <div className="text-[11px] text-slate-400 mt-0.5 line-clamp-2" title={s.goal}>Goal: {s.goal}</div>
            <div className="text-[10px] text-slate-500 mt-0.5 mono truncate" title={s.features.join(", ")}>
              sees: {s.features.map((f) => (
                <span key={f} className={lvlCls(a.evidence?.[f], f)}>{f} </span>
              ))}
            </div>
            <div className="mt-2"><BeliefBars belief={a.belief} prev={a.prevBelief} /></div>
            <div className={`mt-2 text-[11px] truncate ${vetoing ? "text-orange-300 font-semibold" : "text-slate-300"}`}>
              {a.status ?? (a.active ? "joined" : "-")}
              {a.preferred && a.lastType !== "proposal" ? <span className="text-slate-500"> · wants {a.preferred}</span> : null}
            </div>
          </button>
        );
      })}
    </div>
  );
}

function lvlCls(level: string | undefined, f: string) {
  if (!level) return "";
  const abnormal = f === "minutes_since_deploy" ? level === "low" : level !== "low";
  if (!abnormal) return "text-slate-500";
  return level === "medium" ? "text-amber-300" : "text-red-400";
}
