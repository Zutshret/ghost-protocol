import { useEffect, useMemo, useRef, useState } from "react";
import { SENDER_NAME, TYPE_LABEL } from "../labels";
import { SYSTEM_COLOR, type AgentSpec, type Msg } from "../types";

const TYPE_STYLE: Record<string, string> = {
  belief: "bg-sky-500/15 text-sky-300",
  evidence: "bg-teal-500/15 text-teal-300",
  challenge: "bg-fuchsia-500/15 text-fuchsia-300",
  proposal: "bg-indigo-500/15 text-indigo-300",
  accept: "bg-emerald-500/15 text-emerald-300",
  reject: "bg-slate-500/20 text-slate-300",
  veto: "bg-orange-500/25 text-orange-300",
  escalate: "bg-yellow-500/25 text-yellow-200",
  human_response: "bg-green-500/25 text-green-300",
  action: "bg-red-500/25 text-red-200",
  mode_switch: "bg-violet-500/25 text-violet-200",
  recruit: "bg-cyan-500/20 text-cyan-200",
  telemetry: "bg-slate-700/40 text-slate-400",
};

export function colorFor(sender: string, roster: Map<string, AgentSpec>) {
  return roster.get(sender)?.color ?? SYSTEM_COLOR[sender] ?? "#94a3b8";
}

export function nameFor(sender: string, roster: Map<string, AgentSpec>) {
  return roster.get(sender)?.name ?? SENDER_NAME[sender] ?? sender;
}

export function TypeBadge({ type }: { type: string }) {
  return <span className={`text-[9px] uppercase tracking-wide px-1.5 py-0.5 rounded ${TYPE_STYLE[type] ?? ""}`}>{TYPE_LABEL[type] ?? type.replace("_", " ")}</span>;
}

interface Props {
  messages: Msg[];
  roster: Map<string, AgentSpec>;
  selected: number | null;
  onSelect: (m: Msg) => void;
  agentFilter: string | null;
  clearAgentFilter: () => void;
  traceId?: string | null;
}

export default function Ledger({ messages, roster, selected, onSelect, agentFilter, clearAgentFilter, traceId }: Props) {
  const [showVotes, setShowVotes] = useState(true);
  const [follow, setFollow] = useState(true);
  const ref = useRef<HTMLDivElement>(null);

  const rows = useMemo(
    () =>
      messages.filter((m) => {
        if (m.type === "telemetry" && !m.rationale) return false;
        if (!showVotes && (m.type === "accept" || m.type === "reject")) return false;
        if (agentFilter && m.sender !== agentFilter && m.content?.target !== agentFilter && m.content?.to !== agentFilter
          && m.content?.agent !== agentFilter) return false;
        return true;
      }),
    [messages, showVotes, agentFilter],
  );

  useEffect(() => {
    if (follow && ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [rows.length, follow]);

  return (
    <div className="flex flex-col h-full min-h-0">
      <div className="flex items-center gap-3 px-3 py-2 border-b border-slate-800 text-xs">
        <span className="font-semibold text-slate-200">Action ledger</span>
        <span className="text-slate-500">{rows.length} entries</span>
        {traceId && (
          <button onClick={() => navigator.clipboard?.writeText(traceId)} title={`OpenTelemetry trace ${traceId} (click to copy; find it in Grafana / ClickHouse)`}
            className="mono text-[10px] px-1.5 rounded bg-emerald-500/15 text-emerald-300">trace {traceId.slice(0, 12)}…</button>
        )}
        {agentFilter && (
          <button onClick={clearAgentFilter} className="px-1.5 rounded bg-slate-800 text-slate-300">
            only {nameFor(agentFilter, roster)} ✕
          </button>
        )}
        <label className="ml-auto flex items-center gap-1 text-slate-400">
          <input type="checkbox" checked={showVotes} onChange={(e) => setShowVotes(e.target.checked)} /> votes
        </label>
        <label className="flex items-center gap-1 text-slate-400">
          <input type="checkbox" checked={follow} onChange={(e) => setFollow(e.target.checked)} /> follow
        </label>
      </div>
      <div ref={ref} className="flex-1 overflow-y-auto min-h-0">
        {rows.map((m) => {
          const important = ["action", "escalate", "mode_switch", "veto", "recruit", "human_response"].includes(m.type);
          return (
            <button key={m.id} onClick={() => onSelect(m)}
              className={`w-full text-left px-3 py-1.5 border-b border-slate-900 hover:bg-slate-800/60 flex gap-2 items-start
                ${selected === m.id ? "bg-slate-800" : important ? "bg-slate-900/70" : ""}`}>
              <span className="mono text-[10px] text-slate-600 w-8 shrink-0 pt-0.5">t{m.tick}</span>
              <span className="w-24 shrink-0 text-[11px] font-semibold truncate pt-0.5" style={{ color: colorFor(m.sender, roster) }}>
                {nameFor(m.sender, roster).replace(" Agent", "")}
              </span>
              <span className="w-24 shrink-0"><TypeBadge type={m.type} /></span>
              <span className={`text-[11px] leading-snug ${important ? "text-slate-100" : "text-slate-400"} line-clamp-2`}>
                {m.rationale || JSON.stringify(m.content).slice(0, 120)}
              </span>
            </button>
          );
        })}
        {!rows.length && <div className="p-6 text-center text-sm text-slate-500">Start a scenario to see who did what, and why.</div>}
      </div>
    </div>
  );
}
