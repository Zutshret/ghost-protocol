import { useState } from "react";
import type { Msg, Option } from "../types";
import { HYP_COLOR } from "../types";

export default function ApprovalPanel({ esc, onAnswer, onShowProvenance }: {
  esc: Msg;
  onAnswer: (decision: "approve" | "reject", action: string) => Promise<void>;
  onShowProvenance: () => void;
}) {
  const options: Option[] = esc.content.options ?? [];
  const [choice, setChoice] = useState<string>(options[0]?.action ?? "noop");
  const [busy, setBusy] = useState(false);
  const send = async (d: "approve" | "reject") => {
    setBusy(true);
    await onAnswer(d, d === "approve" ? choice : "noop");
    setBusy(false);
  };
  return (
    <div className="fixed inset-0 z-50 bg-black/60 flex items-center justify-center p-4">
      <div className="w-[620px] max-w-full rounded-xl border-2 border-yellow-500/70 bg-slate-950 shadow-2xl">
        <div className="px-5 py-3 border-b border-slate-800 flex items-center gap-2">
          <span className="text-yellow-300 text-lg">⚠</span>
          <span className="font-semibold text-yellow-100">Human approval needed</span>
          <span className="ml-auto mono text-xs text-slate-500">tick {esc.tick}</span>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-slate-300">{esc.rationale}</p>
          <div className="space-y-2">
            {options.map((o) => (
              <label key={o.action}
                className={`flex gap-3 items-start p-3 rounded-lg border cursor-pointer ${choice === o.action ? "border-yellow-400 bg-yellow-500/5" : "border-slate-800 hover:border-slate-600"}`}>
                <input type="radio" className="mt-1" checked={choice === o.action} onChange={() => setChoice(o.action)} />
                <div className="flex-1">
                  <div className="flex items-center gap-2">
                    <span className="mono font-semibold text-slate-100">{o.action}</span>
                    {o.hypothesis && (
                      <span className="text-xs px-1.5 rounded" style={{ background: HYP_COLOR[o.hypothesis] + "33", color: HYP_COLOR[o.hypothesis] }}>
                        fixes {o.hypothesis} · P={o.probability != null ? (o.probability * 100).toFixed(0) + "%" : "-"}
                      </span>
                    )}
                    {o.blocked_without_approval && <span className="text-[10px] px-1 rounded bg-orange-500/20 text-orange-300">needs override</span>}
                  </div>
                  <div className="text-xs text-slate-400 mt-0.5">Risk: {o.risk}</div>
                </div>
              </label>
            ))}
          </div>
          <div className="flex gap-2 items-center">
            <button onClick={onShowProvenance} className="text-xs text-slate-400 underline">why are we asking?</button>
            <button disabled={busy} onClick={() => send("reject")}
              className="ml-auto px-4 py-2 rounded-lg border border-slate-600 text-slate-200 hover:bg-slate-800 disabled:opacity-50">Reject (hold)</button>
            <button disabled={busy} onClick={() => send("approve")}
              className="px-4 py-2 rounded-lg bg-yellow-500 text-slate-950 font-semibold hover:bg-yellow-400 disabled:opacity-50">Approve {choice}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
