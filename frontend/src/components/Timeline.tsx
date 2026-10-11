import { useEffect, useMemo, useRef } from "react";
import { act, hyp, SENDER_NAME } from "../labels";
import type { AgentSpec, Msg } from "../types";
import { pct } from "../useRun";
import { METRIC } from "./ServiceGraph";

// "How they decided": only the moments that tell the story, on one vertical line.
// A challenge and its answer are merged into a single card; votes are hidden.

const FIXES: Record<string, string> = {
  rollback_deploy: "bad_deploy", block_traffic: "attack", failover_db: "db_fault", restart_service: "dependency_timeout",
};

type View = { id: string; top: string; conf: number };
type Item =
  | { kind: "note"; key: number; tick: number; text: string; tone?: "good" | "warn" }
  | { kind: "views"; key: number; tick: number; views: View[] }
  | { kind: "exchange"; key: number; tick: number; from: string; to: string; claim: string; doubt: string; answer?: string }
  | { kind: "changed"; key: number; tick: number; who: string; from: View; to: View; because: string }
  | { kind: "rule"; key: number; tick: number; text: string }
  | { kind: "veto"; key: number; tick: number; text: string }
  | { kind: "human"; key: number; tick: number; text: string }
  | { kind: "decision"; key: number; tick: number; action: string; by: string; detail: string };

const plainEvidence = (ev: Record<string, string> = {}) =>
  Object.entries(ev).map(([f, l]) => `${(METRIC[f]?.label ?? f.replace(/_/g, " ")).toLowerCase()} ${l}`).join(", ");

export function buildTimeline(messages: Msg[], roster: Map<string, AgentSpec>): Item[] {
  const name = (id: string) => roster.get(id)?.name.replace(" Agent", "") ?? SENDER_NAME[id] ?? id;
  const items: Item[] = [];
  const last = new Map<string, View>();
  const joined: string[] = [];

  for (const m of messages) {
    const c = m.content ?? {};
    switch (m.type) {
      case "mode_switch":
        items.push({ kind: "note", key: m.id, tick: m.tick,
          tone: c.mode === "resolved" ? "good" : c.mode === "agents" && c.trigger !== "incident_detected" ? "warn" : undefined,
          text: c.mode === "runbook" ? "Something broke. The fixed rule tries first."
            : c.mode === "resolved" ? "Fixed. Every service is healthy again."
              : c.trigger === "incident_detected" ? "Something broke. The agent team takes over."
                : "The fixed rule's fix didn't work, so the agents take over." });
        break;
      case "recruit":
        if (c.initial) {
          joined.push(name(c.agent));
          const prev = items[items.length - 1];
          const text = `${joined.length} agents join the incident.`;
          if (prev?.kind === "note" && prev.text.endsWith("agents join the incident.")) prev.text = text;
          else items.push({ kind: "note", key: m.id, tick: m.tick, text });
        } else {
          items.push({ kind: "note", key: m.id, tick: m.tick, tone: "warn", text: `${name(c.agent)} is called in for its specialist skill.` });
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
          else items.push({ kind: "views", key: m.id, tick: m.tick, views: [now] });
        } else if (prev.top !== now.top || Math.abs(prev.conf - now.conf) >= 0.15) {
          const peers = Object.keys(c.learned_from ?? {});
          items.push({ kind: "changed", key: m.id, tick: m.tick, who: m.sender, from: prev, to: now,
            because: peers.length ? `after hearing from ${peers.map(name).join(" and ")}` : "after a fresh look" });
        }
        break;
      }
      case "challenge":
        items.push({ kind: "exchange", key: m.id, tick: m.tick, from: m.sender, to: c.target,
          claim: hyp(c.my_hypothesis), doubt: hyp(c.their_hypothesis) });
        break;
      case "evidence":
        if (roster.has(m.sender)) {
          for (let i = items.length - 1; i >= 0; i--) {
            const it = items[i];
            if (it.kind === "exchange" && it.to === m.sender && it.from === c.to && !it.answer) {
              it.answer = plainEvidence(c.evidence) || "no data to share";
              break;
            }
          }
        } else if (c.failed_action) {
          items.push({ kind: "note", key: m.id, tick: m.tick, tone: "warn",
            text: `"${act(c.failed_action)}" didn't help, so it's probably not ${hyp(FIXES[c.failed_action]).toLowerCase()}.` });
        }
        break;
      case "proposal":
        if (m.sender === "runbook" && c.action !== "noop") items.push({ kind: "rule", key: m.id, tick: m.tick, text: `A rule matched, so it will ${act(c.action).toLowerCase()}.` });
        break;
      case "veto":
        items.push({ kind: "veto", key: m.id, tick: m.tick,
          text: m.sender === "validator" ? `Safety check blocks "${act(c.action).toLowerCase()}": ${m.rationale.replace(/^Blocked:\s*/, "").replace(/\.$/, "")}.`
            : `${name(m.sender)} vetoes "${act(c.action).toLowerCase()}".` });
        break;
      case "escalate":
        items.push({ kind: "human", key: m.id, tick: m.tick, text: "Too risky to decide alone, so the team asks a human." });
        break;
      case "human_response":
        items.push({ kind: "human", key: m.id, tick: m.tick,
          text: c.decision === "approve" ? `The human approves: ${act(c.action).toLowerCase()}.` : "The human says: not yet, keep watching." });
        break;
      case "action":
        if (c.action === "probe") items.push({ kind: "note", key: m.id, tick: m.tick, text: "Not sure yet, so they take a closer look first." });
        else {
          const agreed = m.rationale.match(/(\d+)\/(\d+) accepted/);
          items.push({ kind: "decision", key: m.id, tick: m.tick, action: c.action, by: m.sender,
            detail: agreed ? `${agreed[1]} of ${agreed[2]} agents agreed` : m.sender === "human" ? "approved by a human" : m.sender === "runbook" ? "no discussion" : "" });
        }
        break;
    }
  }
  return items;
}

function Name({ id, roster }: { id: string; roster: Map<string, AgentSpec> }) {
  const spec = roster.get(id);
  return <b style={{ color: spec?.color ?? "#e2e8f0" }}>{spec?.name.replace(" Agent", "") ?? SENDER_NAME[id] ?? id}</b>;
}

const ICON: Record<Item["kind"], { glyph: string; ring: string }> = {
  note: { glyph: "•", ring: "border-slate-700 text-slate-400" },
  views: { glyph: "👥", ring: "border-slate-600" },
  exchange: { glyph: "💬", ring: "border-slate-600" },
  changed: { glyph: "↻", ring: "border-violet-400 text-violet-300" },
  rule: { glyph: "⚙", ring: "border-slate-500 text-slate-300" },
  veto: { glyph: "⛔", ring: "border-amber-400" },
  human: { glyph: "🙋", ring: "border-yellow-400" },
  decision: { glyph: "✓", ring: "border-emerald-400 bg-emerald-500/20 text-emerald-300" },
};

export default function Timeline({ messages, roster, onSelect }: {
  messages: Msg[]; roster: Map<string, AgentSpec>; onSelect: (id: number) => void;
}) {
  const items = useMemo(() => buildTimeline(messages, roster), [messages, roster]);
  const ref = useRef<HTMLDivElement>(null);
  useEffect(() => {
    ref.current?.scrollTo({ top: ref.current.scrollHeight, behavior: "smooth" });
  }, [items.length]);

  if (!items.length) {
    return <div className="flex h-full items-center justify-center p-6 text-center text-base text-slate-500">
      Press <b className="mx-1 text-slate-300">Run incident</b> and the story will appear here.
    </div>;
  }
  return (
    <div ref={ref} className="h-full overflow-y-auto pr-1">
      <ol className="relative ml-4 border-l border-slate-800 pb-2">
        {items.map((it) => {
          const icon = ICON[it.kind];
          return (
            <li key={it.key} className="relative mb-3 pl-7">
              <span className={`absolute -left-[15px] top-0.5 flex h-[30px] w-[30px] items-center justify-center rounded-full border bg-slate-950 text-sm ${icon.ring}`}>{icon.glyph}</span>
              <button onClick={() => onSelect(it.key)} className="block w-full text-left">
                <Body it={it} roster={roster} />
              </button>
            </li>
          );
        })}
      </ol>
    </div>
  );
}

function Body({ it, roster }: { it: Item; roster: Map<string, AgentSpec> }) {
  const time = <span className="ml-2 text-xs font-normal tabular-nums text-slate-600">min {it.tick}</span>;
  switch (it.kind) {
    case "note":
      return <p className={`pt-1 text-[15px] ${it.tone === "good" ? "font-semibold text-emerald-300" : it.tone === "warn" ? "text-amber-200" : "text-slate-400"}`}>{it.text}{time}</p>;
    case "rule":
      return <p className="pt-1 text-[15px] text-slate-300"><b className="text-slate-200">Fixed rule:</b> {it.text}{time}</p>;
    case "views":
      return (
        <div className="pt-0.5">
          <p className="text-[15px] text-slate-300">First guesses, each from its own data{time}</p>
          <div className="mt-2 flex flex-wrap gap-1.5">
            {it.views.map((v) => (
              <span key={v.id} className="rounded-full border border-slate-800 bg-slate-900 px-2.5 py-1 text-sm">
                <Name id={v.id} roster={roster} /> <span className="text-slate-300">{hyp(v.top)}</span> <span className="text-slate-500">{pct(v.conf)}</span>
              </span>
            ))}
          </div>
        </div>
      );
    case "exchange":
      return (
        <div className="rounded-xl border border-slate-800 bg-slate-900/60 px-3.5 py-2.5 hover:border-slate-600">
          <p className="text-[15px] text-slate-200"><Name id={it.from} roster={roster} /> questions <Name id={it.to} roster={roster} />:
            <span className="text-slate-300"> "I think it's {it.claim.toLowerCase()}, not {it.doubt.toLowerCase()}. What's your evidence?"</span>{time}</p>
          {it.answer && <p className="mt-1 text-sm text-slate-400">↳ <Name id={it.to} roster={roster} /> shares its data: {it.answer}</p>}
        </div>
      );
    case "changed":
      return (
        <div className="rounded-xl border border-violet-500/50 bg-violet-500/10 px-3.5 py-2.5">
          <p className="text-[15px] text-slate-200"><Name id={it.who} roster={roster} /> changes its mind {it.because}{time}</p>
          <p className="mt-0.5 text-base"><span className="text-slate-500 line-through">{hyp(it.from.top)} {pct(it.from.conf)}</span>
            <span className="mx-2 text-violet-300">→</span><b className="text-white">{hyp(it.to.top)} {pct(it.to.conf)}</b></p>
        </div>
      );
    case "veto":
      return <div className="rounded-xl border border-amber-500/50 bg-amber-500/10 px-3.5 py-2.5 text-[15px] text-amber-100">{it.text}{time}</div>;
    case "human":
      return <div className="rounded-xl border border-yellow-400/40 bg-yellow-400/10 px-3.5 py-2.5 text-[15px] text-yellow-100">{it.text}{time}</div>;
    case "decision":
      return (
        <div className="rounded-xl border border-emerald-500/50 bg-emerald-500/10 px-3.5 py-2.5">
          <p className="text-xs font-semibold uppercase tracking-wider text-emerald-300">Action taken{time}</p>
          <p className="text-lg font-semibold text-white">{act(it.action)}</p>
          <p className="text-sm text-slate-400">by <Name id={it.by} roster={roster} />{it.detail ? ` · ${it.detail}` : ""}</p>
        </div>
      );
  }
}
