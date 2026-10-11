import { useState } from "react";
import { act, hyp } from "../labels";
import type { Msg, Option } from "../types";
import Info from "./Info";

function plainReason(esc: Msg): string {
  const r: string = esc.content.reason ?? esc.rationale.replace(/^Asking a human:\s*/, "");
  const blocked = r.match(/validator blocked (\w+)/);
  if (blocked) return `The agents wanted to ${act(blocked[1]).toLowerCase()}, but the safety check blocked it. Only a person can accept that risk.`;
  if (/no proposal reached/.test(r)) return "The agents couldn't agree on a safe fix after several rounds of discussion.";
  return r.charAt(0).toUpperCase() + r.slice(1);
}

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
  const llmBriefing = esc.rationale && !esc.rationale.startsWith("Asking a human:") ? esc.rationale : null;
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/65 p-4">
      <div className="w-[720px] max-w-full rounded-2xl border border-yellow-400/60 bg-slate-950 shadow-2xl">
        <div className="flex items-center gap-3 border-b border-slate-800 px-6 py-4">
          <span className="text-2xl">🙋</span>
          <div>
            <div className="text-lg font-semibold text-white">The agents need your decision</div>
            <div className="text-sm text-slate-400">Minute {esc.tick} · nothing happens until you choose</div>
          </div>
        </div>
        <div className="space-y-4 px-6 py-5">
          <p className="text-[15px] leading-relaxed text-slate-200">{llmBriefing ?? plainReason(esc)}</p>
          <div className="space-y-2">
            {options.map((o) => (
              <label key={o.action}
                className={`flex cursor-pointer items-start gap-3 rounded-xl border p-3 transition-colors ${choice === o.action ? "border-yellow-400 bg-yellow-400/5" : "border-slate-800 hover:border-slate-600"}`}>
                <input type="radio" className="mt-1.5" checked={choice === o.action} onChange={() => setChoice(o.action)} />
                <div className="flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <span className="font-semibold text-slate-50">{act(o.action)}</span>
                    {o.hypothesis && o.probability != null && (
                      <span className="rounded-full bg-slate-800 px-2 py-0.5 text-xs text-slate-300">
                        right if it's {hyp(o.hypothesis).toLowerCase()} · {Math.round(o.probability * 100)}% likely
                      </span>
                    )}
                    {o.blocked_without_approval && (
                      <span className="rounded-full bg-amber-500/15 px-2 py-0.5 text-xs text-amber-300">needs your override
                        <Info text="The safety check blocks this action unless a person explicitly accepts the risk." /></span>
                    )}
                  </div>
                  <div className="mt-0.5 text-sm text-slate-400">Risk: {o.risk === "safe" ? "none known" : o.risk}</div>
                </div>
              </label>
            ))}
          </div>
          <div className="flex items-center gap-2 pt-1">
            <button onClick={onShowProvenance} className="whitespace-nowrap text-sm text-violet-300 hover:text-violet-200">Why are we asking? →</button>
            <button disabled={busy} onClick={() => send("reject")}
              className="ml-auto whitespace-nowrap rounded-lg border border-slate-600 px-4 py-2 text-slate-200 hover:bg-slate-800 disabled:opacity-50">Not now</button>
            <button disabled={busy} onClick={() => send("approve")}
              className="whitespace-nowrap rounded-lg bg-yellow-400 px-4 py-2 font-semibold text-slate-950 hover:bg-yellow-300 disabled:opacity-50">Approve: {act(choice).toLowerCase()}</button>
          </div>
        </div>
      </div>
    </div>
  );
}
