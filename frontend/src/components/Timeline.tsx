import { useEffect, useMemo, useRef } from "react";
import { act, hyp, SENDER_NAME } from "../labels";
import type { AgentSpec, Msg } from "../types";
import { pct } from "../useRun";

// Which cause each fix addresses (for "X didn't help" lines).
const FIXES: Record<string, string> = {
  rollback_deploy: "bad_deploy", block_traffic: "attack", failover_db: "db_fault", restart_service: "dependency_timeout",
};

type View = { id: string; top: string; conf: number };
type Item =
  | { kind: "status"; key: number; tick: number; text: string; tone?: "good" | "warn" }
  | { kind: "views"; key: number; tick: number; title: string; views: View[] }
  | { kind: "changed"; key: number; tick: number; who: string; from: View; to: View; because: string }
  | { kind: "bubble"; key: number; tick: number; who: string; to?: string; text: string; reply?: boolean }
  | { kind: "veto"; key: number; tick: number; who: string; text: string }
  | { kind: "human"; key: number; tick: number; text: string }
  | { kind: "decision"; key: number; tick: number; msg: Msg };

export function buildTimeline(messages: Msg[], roster: Map<string, AgentSpec>): Item[] {
  const name = (id: string) => roster.get(id)?.name.replace(" Agent", "") ?? SENDER_NAME[id] ?? id;
  const items: Item[] = [];
  const last = new Map<string, View>();
  let joined: string[] = [];

  for (const m of messages) {
    const c = m.content ?? {};
    switch (m.type) {
      case "mode_switch": {
        const text = c.mode === "runbook" ? "Incident detected. The fixed rule goes first."
          : c.mode === "resolved" ? "Recovered: every service is healthy again."
            : c.trigger === "incident_detected" ? "Incident detected. Handed to the agent team."
              : `The agents take over: ${String(c.trigger ?? "").replace(/_/g, " ")}.`;
        items.push({ kind: "status", key: m.id, tick: m.tick, text, tone: c.mode === "resolved" ? "good" : c.mode === "agents" && c.trigger !== "incident_detected" ? "warn" : undefined });
        break;
      }
      case "recruit":
        if (c.initial) {
          joined.push(name(c.agent));
          const prev = items[items.length - 1];
          const text = `${joined.length} agents join, each chosen for its skills: ${joined.join(", ")}.`;
          if (prev?.kind === "status" && prev.text.includes("agents join")) prev.text = text;
          else items.push({ kind: "status", key: m.id, tick: m.tick, text });
        } else {
          items.push({ kind: "status", key: m.id, tick: m.tick, tone: "warn",
            text: `${name(c.agent)} is called in mid-incident. ${m.rationale.split(": ").slice(1).join(": ").split(";")[0]}.` });
        }
        break;
      case "belief": {
        if (!roster.has(m.sender)) break;
        const now: View = { id: m.sender, top: c.top, conf: c.confidence };
        const prev = last.get(m.sender);
        last.set(m.sender, now);
        if (!prev) {
          const tail = items[items.length - 1];
          if (tail?.kind === "views" && tail.tick === m.tick) tail.views.push(now);
          else items.push({ kind: "views", key: m.id, tick: m.tick, title: "First impressions, each from its own data only", views: [now] });
        } else if (prev.top !== now.top || Math.abs(prev.conf - now.conf) >= 0.15) {
          const peers = Object.keys(c.learned_from ?? {});
          const because = peers.length ? `after ${peers.map(name).join(" and ")}'s evidence` : "after a fresh look at its data";
          items.push({ kind: "changed", key: m.id, tick: m.tick, who: m.sender, from: prev, to: now, because });
        }
        break;
      }
      case "challenge":
        items.push({ kind: "bubble", key: m.id, tick: m.tick, who: m.sender, to: c.target, text: m.rationale.replace(/^@\w+:\s*/, "") });
        break;
      case "evidence":
        if (roster.has(m.sender)) {
          items.push({ kind: "bubble", key: m.id, tick: m.tick, who: m.sender, to: c.to, reply: true, text: m.rationale.replace(/^@\w+:\s*/, "") });
        } else if (c.failed_action) {
          items.push({ kind: "status", key: m.id, tick: m.tick, tone: "warn",
            text: `"${act(c.failed_action)}" didn't help, which counts as evidence against "${hyp(FIXES[c.failed_action])}".` });
        }
        break;
      case "proposal":
        if (m.sender === "runbook" && c.action !== "noop") {
          items.push({ kind: "bubble", key: m.id, tick: m.tick, who: "runbook", text: `Rule matched (${c.rule?.replace(/_/g, " ")}): ${act(c.action).toLowerCase()}.` });
        } else if (m.sender === "aggregator") {
          items.push({ kind: "bubble", key: m.id, tick: m.tick, who: "aggregator", text: m.rationale });
        }
        break;
      case "veto":
        items.push({ kind: "veto", key: m.id, tick: m.tick, who: m.sender,
          text: `${m.sender === "validator" ? "Safety check blocks" : `${name(m.sender)} vetoes`} "${act(c.action)}": ${m.rationale.replace(/^Blocked:\s*/, "")}` });
        break;
      case "escalate":
        items.push({ kind: "human", key: m.id, tick: m.tick, text: `The team asks a human. ${m.rationale.replace(/^Asking a human:\s*/, "")}` });
        break;
      case "human_response":
        items.push({ kind: "human", key: m.id, tick: m.tick,
          text: c.decision === "approve" ? `Human approved: ${act(c.action).toLowerCase()}.` : "Human said no: hold and keep watching." });
        break;
      case "action":
        if (c.action === "probe") items.push({ kind: "status", key: m.id, tick: m.tick, text: `${name(m.sender)} takes a closer look (probe) before acting.` });
        else items.push({ kind: "decision", key: m.id, tick: m.tick, msg: m });
        break;
      case "telemetry":
        if (c.event === "summary") items.push({ kind: "status", key: m.id, tick: m.tick, tone: "good", text: c.summary });
        break;
    }
  }
  return items;
}

function Who({ id, roster }: { id: string; roster: Map<string, AgentSpec> }) {
  const spec = roster.get(id);
  return (
    <span className="inline-flex items-center gap-1.5 font-semibold" style={{ color: spec?.color ?? "#cbd5e1" }}>
      <span className="h-2 w-2 rounded-full" style={{ background: spec?.color ?? "#64748b" }} />
      {spec?.name.replace(" Agent", "") ?? SENDER_NAME[id] ?? id}
    </span>
  );
}

export default function Timeline({ messages, roster, onSelect }: {
  messages: Msg[]; roster: Map<string, AgentSpec>; onSelect: (id: number) => void;
}) {
  const items = useMemo(() => buildTimeline(messages, roster), [messages, roster]);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [items.length]);

  if (!items.length) {
    return <div className="flex h-full items-center justify-center p-6 text-center text-sm text-slate-500">
      Press <b className="mx-1 text-slate-300">Run incident</b> to watch the response unfold here.
    </div>;
  }
  return (
    <div ref={ref} className="h-full space-y-2.5 overflow-y-auto px-1 pb-2">
      {items.map((it) => {
        const click = () => onSelect(it.key);
        switch (it.kind) {
          case "status":
            return <button key={it.key} onClick={click} className={`block w-full rounded-lg px-3 py-1.5 text-left text-sm
              ${it.tone === "good" ? "bg-emerald-500/10 text-emerald-200" : it.tone === "warn" ? "bg-amber-500/10 text-amber-200" : "text-slate-400"}`}>
              <span className="mr-2 text-[11px] tabular-nums text-slate-500">t{it.tick}</span>{it.text}</button>;
          case "views":
            return <div key={it.key} className="rounded-xl border border-slate-800 bg-slate-900/50 p-3">
              <div className="mb-2 text-xs text-slate-400">{it.title}</div>
              <div className="flex flex-wrap gap-2">
                {it.views.map((v) => <span key={v.id} className="rounded-lg bg-slate-800/80 px-2 py-1 text-xs">
                  <Who id={v.id} roster={roster} /> <span className="text-slate-300">{hyp(v.top)} {pct(v.conf)}</span></span>)}
              </div>
            </div>;
          case "changed":
            return <button key={it.key} onClick={click} className="block w-full rounded-xl border border-violet-500/50 bg-violet-500/10 p-3 text-left">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-violet-300">Changed its mind</div>
              <div className="mt-1 text-sm"><Who id={it.who} roster={roster} />: <span className="text-slate-400 line-through decoration-slate-600">{hyp(it.from.top)} {pct(it.from.conf)}</span>
                <span className="mx-1.5 text-violet-300">→</span><b className="text-white">{hyp(it.to.top)} {pct(it.to.conf)}</b>
                <span className="text-slate-400"> {it.because}</span></div>
            </button>;
          case "bubble":
            return <button key={it.key} onClick={click} className={`block w-full text-left ${it.reply ? "pl-8" : ""}`}>
              <div className="mb-0.5 text-xs"><Who id={it.who} roster={roster} />{it.to && <span className="text-slate-500"> {it.reply ? "replies to" : "to"} {roster.get(it.to)?.name.replace(" Agent", "") ?? it.to}</span>}</div>
              <div className={`rounded-2xl rounded-tl-sm border px-3 py-2 text-sm leading-snug ${it.reply ? "border-slate-800 bg-slate-900/40 text-slate-400" : "border-slate-700/80 bg-slate-800/60 text-slate-200"}`}
                style={{ borderLeftColor: roster.get(it.who)?.color, borderLeftWidth: 3 }}>{it.text}</div>
            </button>;
          case "veto":
            return <button key={it.key} onClick={click} className="block w-full rounded-xl border border-amber-500/60 bg-amber-500/10 px-3 py-2 text-left text-sm text-amber-100">
              <span className="mr-1 font-semibold text-amber-300">⛔ Veto.</span>{it.text}</button>;
          case "human":
            return <button key={it.key} onClick={click} className="block w-full rounded-xl border border-yellow-400/50 bg-yellow-400/10 px-3 py-2 text-left text-sm text-yellow-100">
              <span className="mr-1">🙋</span>{it.text}</button>;
          case "decision": {
            const m = it.msg;
            return <button key={it.key} onClick={click} className="block w-full rounded-xl border border-emerald-500/50 bg-emerald-500/10 px-3 py-2 text-left">
              <div className="text-[11px] font-semibold uppercase tracking-wider text-emerald-300">Action taken · t{it.tick}</div>
              <div className="text-base font-semibold text-white">{act(m.content.action)}</div>
              <div className="text-xs text-slate-400">by <Who id={m.sender} roster={roster} /></div>
            </button>;
          }
        }
      })}
    </div>
  );
}
