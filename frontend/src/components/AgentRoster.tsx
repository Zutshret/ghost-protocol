import { useState } from "react";
import { HYPOTHESES, HYP_COLOR } from "../types";
import { act, hyp, TYPE_LABEL } from "../labels";
import { pct, type AgentView } from "../useRun";
import Info from "./Info";

const BADGE_HELP = {
  veto: "Safety-critical: this agent can block a risky action on its own.",
  specialist: "A specialist that isn't on the default team; it's called in only when its skill is needed.",
  agntcy: "This agent's card is published in the AGNTCY Directory, so other systems can discover it.",
};

function FullBeliefs({ belief }: { belief?: Record<string, number> }) {
  return (
    <div className="space-y-1">
      {HYPOTHESES.map((h) => {
        const p = belief?.[h] ?? 0;
        return (
          <div key={h} className="flex items-center gap-2 text-xs">
            <span className="w-28 text-slate-400">{hyp(h)}</span>
            <div className="h-1.5 flex-1 overflow-hidden rounded bg-slate-800">
              <div className="h-full rounded transition-all duration-700" style={{ width: `${p * 100}%`, background: HYP_COLOR[h] }} />
            </div>
            <span className="w-9 text-right tabular-nums text-slate-300">{belief ? pct(p) : ""}</span>
          </div>
        );
      })}
    </div>
  );
}

function AgentCard({ a, cid, onFilter }: { a: AgentView; cid?: string; onFilter: () => void }) {
  const [open, setOpen] = useState(false);
  const s = a.spec;
  const top = a.belief ? Object.entries(a.belief).sort((x, y) => y[1] - x[1])[0] : null;
  const vetoing = a.lastType === "veto";
  const doing = a.lastType ? (TYPE_LABEL[a.lastType] ?? a.lastType) : "";
  return (
    <div className={`rounded-xl border bg-slate-900/60 p-3 transition-all duration-500
        ${a.active ? "border-slate-700/80" : "border-slate-800/60 opacity-45"} ${vetoing ? "!border-amber-400" : ""}
        ${a.recruitedMidIncident ? "ring-1 ring-violet-400/60" : ""}`}>
      <div className="flex items-center gap-1.5">
        <span className="h-2.5 w-2.5 rounded-full" style={{ background: s.color }} />
        <span className="font-semibold text-slate-100">{s.name.replace(" Agent", "")}</span>
        {s.safety_critical && <span className="rounded bg-amber-500/15 px-1.5 text-[10px] font-medium text-amber-300">VETO<Info text={BADGE_HELP.veto} /></span>}
        {!s.core && <span className="rounded bg-violet-500/15 px-1.5 text-[10px] font-medium text-violet-300">SPECIALIST<Info text={BADGE_HELP.specialist} /></span>}
        <span className="ml-auto text-[11px] text-slate-500">{a.active ? "" : s.core ? "waiting" : "on call"}</span>
      </div>
      <div className="mt-0.5 truncate text-xs text-slate-400" title={s.goal}>{s.goal}</div>

      <div className="mt-2.5">
        {top ? (
          <>
            <div className="flex items-baseline justify-between">
              <span className="text-sm text-slate-300">thinks <b className="font-semibold text-white">{hyp(top[0])}</b></span>
              <span className="text-lg font-semibold tabular-nums text-white">{pct(top[1])}</span>
            </div>
            <div className="mt-1 h-2 overflow-hidden rounded-full bg-slate-800">
              <div className="h-full rounded-full bg-violet-500 transition-all duration-700 ease-out" style={{ width: `${top[1] * 100}%` }} />
            </div>
          </>
        ) : (
          <div className="text-sm text-slate-500">{a.active ? "reading its data…" : "not involved yet"}</div>
        )}
      </div>

      <div className={`mt-2 truncate text-xs ${vetoing ? "font-semibold text-amber-300" : "text-slate-400"}`}>
        {doing && <span>Last: {doing.toLowerCase()}</span>}
        {a.preferred && a.preferred !== "probe" ? <span className="text-slate-500"> · wants to {act(a.preferred).toLowerCase()}</span> : null}
      </div>

      <button onClick={() => setOpen((o) => !o)} className="mt-2 text-[11px] text-slate-500 hover:text-slate-300">
        {open ? "Hide details ▴" : "Details ▾"}
      </button>
      {open && (
        <div className="mt-2 space-y-2 border-t border-slate-800 pt-2 text-xs">
          <FullBeliefs belief={a.belief} />
          <div className="text-slate-400">Sees only: <span className="text-slate-300">{s.features.join(", ")}</span></div>
          {a.rationale && <div className="text-slate-400">Says: <span className="text-slate-300">{a.rationale}</span></div>}
          {a.recruitedWhy && <div className="text-slate-400">Why chosen: <span className="text-slate-300">{a.recruitedWhy}</span></div>}
          {cid && <div className="text-slate-400">AGNTCY record<Info text={BADGE_HELP.agntcy} />: <span className="break-all font-mono text-[10px] text-emerald-300">{cid}</span></div>}
          <button onClick={onFilter} className="text-violet-300 hover:text-violet-200">Show this agent's messages →</button>
        </div>
      )}
    </div>
  );
}

export default function AgentRoster({ agents, onSelect, cids }: {
  agents: AgentView[]; onSelect: (id: string) => void; cids?: Record<string, string>;
}) {
  return (
    <div className="grid grid-cols-2 gap-3 xl:grid-cols-3">
      {agents.map((a) => <AgentCard key={a.spec.id} a={a} cid={cids?.[a.spec.id]} onFilter={() => onSelect(a.spec.id)} />)}
    </div>
  );
}
