import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useMemo } from "react";
import type { Health, ServiceState } from "../types";

const HEALTH: Record<Health, { box: string; dot: string; label: string; text: string }> = {
  green: { box: "border-slate-700/80 bg-slate-900/70", dot: "bg-emerald-400", label: "Healthy", text: "text-emerald-300" },
  yellow: { box: "border-amber-400/70 bg-amber-950/30", dot: "bg-amber-400", label: "Degraded", text: "text-amber-300" },
  red: { box: "border-red-500 bg-red-950/40 shadow-[0_0_24px_-4px_rgba(239,68,68,0.55)]", dot: "bg-red-500 animate-pulse", label: "Failing", text: "text-red-300" },
};

export const SERVICE_ABOUT: Record<string, string> = {
  gateway: "Gateway: the front door; every customer request comes in here.",
  auth: "Auth: checks who is logging in.",
  payments: "Payments: processes card payments.",
  database: "Database: stores accounts and transactions.",
};

// The two numbers worth showing on each node; the rest appear on hover.
const KEY_METRICS: Record<string, string[]> = {
  gateway: ["edge_error_rate", "request_rate"],
  auth: ["failed_logins", "traffic_anomaly"],
  payments: ["payment_error_rate", "latency_ms"],
  database: ["replication_lag_s", "slow_queries"],
};

export const METRIC: Record<string, { label: string; fmt: (v: number) => string }> = {
  request_rate: { label: "Requests/s", fmt: (v) => v.toFixed(0) },
  edge_error_rate: { label: "Error rate", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  upstream_timeouts: { label: "Timeouts", fmt: (v) => v.toFixed(0) },
  failed_logins: { label: "Failed logins", fmt: (v) => v.toFixed(0) },
  suspicious_sources: { label: "Suspicious IPs", fmt: (v) => v.toFixed(0) },
  traffic_anomaly: { label: "Traffic anomaly", fmt: (v) => v.toFixed(2) },
  payment_error_rate: { label: "Payment errors", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  queue_depth: { label: "Queue", fmt: (v) => v.toFixed(0) },
  latency_ms: { label: "Latency", fmt: (v) => `${v.toFixed(0)} ms` },
  replication_lag_s: { label: "Replica lag", fmt: (v) => `${v.toFixed(1)} s` },
  slow_queries: { label: "Slow queries", fmt: (v) => v.toFixed(0) },
  lock_waits: { label: "Lock waits", fmt: (v) => v.toFixed(0) },
  conn_pool_saturation: { label: "Pool use", fmt: (v) => `${(v * 100).toFixed(0)}%` },
  minutes_since_deploy: { label: "Minutes since last release", fmt: (v) => v.toFixed(0) },
  canary_error_rate: { label: "Canary errors", fmt: (v) => `${(v * 100).toFixed(1)}%` },
  config_changes: { label: "Config changes", fmt: (v) => v.toFixed(0) },
  downstream_p99_ms: { label: "p99", fmt: (v) => `${v.toFixed(0)} ms` },
};

const POS: Record<string, { x: number; y: number }> = {
  gateway: { x: 300, y: 0 },
  auth: { x: 0, y: 175 },
  payments: { x: 560, y: 175 },
  database: { x: 560, y: 350 },
};

const EDGES: [string, string][] = [
  ["gateway", "auth"],
  ["gateway", "payments"],
  ["payments", "database"],
];

type SvcData = { name: string; svc?: ServiceState };

const lvl = (l?: string) => (l === "high" ? "text-red-300" : l === "medium" ? "text-amber-200" : "text-slate-200");

function ServiceNode({ data }: NodeProps<Node<SvcData>>) {
  const h = HEALTH[data.svc?.health ?? "green"];
  const values = data.svc?.values ?? {};
  const keys = (KEY_METRICS[data.name] ?? []).filter((k) => k in values);
  const shown = (keys.length ? keys : Object.keys(values)).slice(0, 2);
  const all = Object.keys(values);
  return (
    <div className={`group relative w-72 rounded-2xl border-2 px-5 py-4 transition-all duration-700 ${h.box}`}>
      <Handle type="target" position={Position.Top} className="!border-0 !bg-slate-600" />
      <div className="flex items-center gap-2">
        <span className={`h-3.5 w-3.5 rounded-full transition-colors duration-700 ${h.dot}`} />
        <span className="text-xl font-semibold capitalize text-slate-50">{data.name}</span>
        <span className={`ml-auto text-base font-semibold ${h.text}`}>{h.label}</span>
      </div>
      <div className="mt-2.5 space-y-1.5">
        {shown.length ? shown.map((k) => (
          <div key={k} className="flex justify-between text-base">
            <span className="text-slate-400">{METRIC[k]?.label ?? k}</span>
            <span className={`tabular-nums ${lvl(data.svc?.levels[k])}`}>{METRIC[k]?.fmt(values[k]) ?? values[k]}</span>
          </div>
        )) : <div className="text-base text-slate-500">waiting for data</div>}
      </div>
      {/* full metrics on hover */}
      <div className="pointer-events-none absolute left-1/2 top-full z-50 mt-2 w-64 -translate-x-1/2 rounded-lg border border-slate-700 bg-slate-900 p-3 text-xs opacity-0 shadow-2xl transition-opacity duration-150 group-hover:opacity-100">
        <div className="mb-1.5 leading-snug text-slate-300">{SERVICE_ABOUT[data.name]}</div>
        {all.map((k) => (
          <div key={k} className="flex justify-between py-0.5">
            <span className="text-slate-400">{METRIC[k]?.label ?? k}</span>
            <span className={`tabular-nums ${lvl(data.svc?.levels[k])}`}>{METRIC[k]?.fmt(values[k]) ?? values[k]}</span>
          </div>
        ))}
      </div>
      <Handle type="source" position={Position.Bottom} className="!border-0 !bg-slate-600" />
    </div>
  );
}

const nodeTypes = { svc: ServiceNode };

export default function ServiceGraph({ services }: { services: Record<string, ServiceState> }) {
  const nodes: Node<SvcData>[] = useMemo(
    () => Object.entries(POS).map(([id, position]) => ({
      id, position, type: "svc", data: { name: id, svc: services[id] }, draggable: false,
    })),
    [services],
  );
  const edges: Edge[] = useMemo(
    () => EDGES.map(([s, t]) => {
      const bad = services[t]?.health === "red" || services[s]?.health === "red";
      return { id: `${s}-${t}`, source: s, target: t, animated: bad,
        style: { stroke: bad ? "#f87171" : "#334155", strokeWidth: 2.5, transition: "stroke 0.7s" } };
    }),
    [services],
  );
  return (
    <div className="h-[460px] w-full xl:h-[540px]">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.03, maxZoom: 1.5 }}
        proOptions={{ hideAttribution: true }} nodesConnectable={false} elementsSelectable={false}
        panOnDrag={false} zoomOnScroll={false} zoomOnPinch={false} zoomOnDoubleClick={false} preventScrolling={false}>
        <Background color="#1e293b" gap={22} />
      </ReactFlow>
    </div>
  );
}
