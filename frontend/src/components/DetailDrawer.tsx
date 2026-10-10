import type { AgentSpec, Msg } from "../types";
import { HYP_COLOR } from "../types";
import { TypeBadge, colorFor, nameFor } from "./Ledger";

// Decision provenance (B9): follow content.provenance ids back to the messages
// and evidence that led to a decision.
function provenanceOf(m: Msg, byId: Map<number, Msg>): Msg[] {
  const ids: number[] = m.content?.provenance ?? [];
  return ids.map((id) => byId.get(id)).filter((x): x is Msg => !!x);
}

function BeliefMini({ belief }: { belief: Record<string, number> }) {
  return (
    <div className="flex h-2 w-40 rounded overflow-hidden bg-slate-800">
      {Object.entries(belief).map(([h, p]) => (
        <div key={h} title={`${h} ${(p * 100).toFixed(0)}%`} style={{ width: `${p * 100}%`, background: HYP_COLOR[h] }} />
      ))}
    </div>
  );
}

export default function DetailDrawer({ msg, byId, roster, onClose, onSelect }: {
  msg: Msg; byId: Map<number, Msg>; roster: Map<string, AgentSpec>; onClose: () => void; onSelect: (m: Msg) => void;
}) {
  const chain = provenanceOf(msg, byId);
  const counts = chain.reduce<Record<string, number>>((acc, m) => ({ ...acc, [m.type]: (acc[m.type] ?? 0) + 1 }), {});
  const belief = msg.content?.belief ?? msg.content?.pooled;
  return (
    <div className="fixed inset-y-0 right-0 w-[520px] max-w-full bg-slate-950 border-l border-slate-700 shadow-2xl z-40 flex flex-col">
      <div className="flex items-center gap-2 px-4 py-3 border-b border-slate-800">
        <span className="font-semibold" style={{ color: colorFor(msg.sender, roster) }}>{nameFor(msg.sender, roster)}</span>
        <TypeBadge type={msg.type} />
        <span className="mono text-xs text-slate-500">#{msg.id} · tick {msg.tick}</span>
        <button onClick={onClose} className="ml-auto text-slate-400 hover:text-white text-lg">✕</button>
      </div>
      <div className="flex-1 overflow-y-auto p-4 space-y-4 text-sm">
        <p className="text-slate-100 leading-relaxed">{msg.rationale || "(no rationale)"}</p>
        {belief && typeof belief === "object" && (
          <div className="space-y-1">
            <div className="text-xs text-slate-500 uppercase">Belief</div>
            {Object.entries(belief as Record<string, number>).map(([h, p]) => (
              <div key={h} className="flex items-center gap-2 text-xs">
                <span className="w-32 text-slate-400">{h}</span>
                <div className="flex-1 h-2 rounded bg-slate-800"><div className="h-2 rounded" style={{ width: `${p * 100}%`, background: HYP_COLOR[h] }} /></div>
                <span className="mono w-10 text-right">{(p * 100).toFixed(0)}%</span>
              </div>
            ))}
          </div>
        )}
        {chain.length > 0 && (
          <div>
            <div className="text-xs text-slate-500 uppercase mb-1">
              Provenance: {chain.length} messages led here ({Object.entries(counts).map(([k, v]) => `${v} ${k}`).join(", ")})
            </div>
            <ol className="border-l border-slate-700 ml-1 space-y-1">
              {chain.map((m) => (
                <li key={m.id}>
                  <button onClick={() => onSelect(m)} className="w-full text-left pl-3 py-1 hover:bg-slate-900 rounded-r flex gap-2 items-start">
                    <span className="mono text-[10px] text-slate-600 w-8 shrink-0">#{m.id}</span>
                    <span className="text-[11px] font-semibold w-20 shrink-0 truncate" style={{ color: colorFor(m.sender, roster) }}>
                      {nameFor(m.sender, roster).replace(" Agent", "")}
                    </span>
                    <TypeBadge type={m.type} />
                    <span className="text-[11px] text-slate-400 line-clamp-2 flex-1">{m.rationale}</span>
                    {m.content?.belief && <BeliefMini belief={m.content.belief} />}
                  </button>
                </li>
              ))}
            </ol>
          </div>
        )}
        <details>
          <summary className="text-xs text-slate-500 cursor-pointer">Raw message</summary>
          <pre className="mono text-[10px] text-slate-400 bg-slate-900 p-2 rounded mt-1 overflow-x-auto">{JSON.stringify(msg, null, 2)}</pre>
        </details>
      </div>
    </div>
  );
}
