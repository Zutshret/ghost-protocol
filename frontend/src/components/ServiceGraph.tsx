import { Background, Handle, Position, ReactFlow, type Edge, type Node, type NodeProps } from "@xyflow/react";
import { useMemo } from "react";
import type { Health, ServiceState } from "../types";

const HEALTH: Record<Health, { ring: string; dot: string; label: string }> = {
  green: { ring: "border-emerald-500/60", dot: "bg-emerald-400", label: "healthy" },
  yellow: { ring: "border-amber-400/80", dot: "bg-amber-400", label: "degraded" },
  red: { ring: "border-red-500", dot: "bg-red-500 animate-pulse", label: "failing" },
};

const POS: Record<string, { x: number; y: number }> = {
  gateway: { x: 250, y: 0 },
  auth: { x: 60, y: 110 },
  payments: { x: 440, y: 110 },
  database: { x: 300, y: 230 },
  cache: { x: 580, y: 230 },
};

const EDGES: [string, string][] = [
  ["gateway", "auth"],
  ["gateway", "payments"],
  ["payments", "database"],
  ["payments", "cache"],
];

type SvcData = { name: string; svc?: ServiceState };

function ServiceNode({ data }: NodeProps<Node<SvcData>>) {
  const h = HEALTH[data.svc?.health ?? "green"];
  const vals = Object.entries(data.svc?.values ?? {}).slice(0, 3);
  return (
    <div className={`rounded-lg border-2 ${h.ring} bg-slate-900/95 px-3 py-2 w-44 shadow-lg transition-colors duration-500`}>
      <Handle type="target" position={Position.Top} className="!bg-slate-600 !border-0" />
      <div className="flex items-center gap-2">
        <span className={`h-2.5 w-2.5 rounded-full ${h.dot}`} />
        <span className="font-semibold text-sm text-slate-100">{data.name}</span>
        <span className="ml-auto text-[10px] uppercase tracking-wide text-slate-400">{h.label}</span>
      </div>
      <div className="mt-1 space-y-0.5">
        {vals.map(([k, v]) => (
          <div key={k} className="flex justify-between text-[10px] mono">
            <span className="text-slate-500 truncate">{k}</span>
            <span className={levelColor(data.svc?.levels[k])}>{fmt(v)}</span>
          </div>
        ))}
      </div>
      <Handle type="source" position={Position.Bottom} className="!bg-slate-600 !border-0" />
    </div>
  );
}

const levelColor = (l?: string) =>
  l === "high" ? "text-red-400" : l === "medium" ? "text-amber-300" : "text-slate-300";
const fmt = (v: number) => (v < 1 ? v.toFixed(3) : v < 100 ? v.toFixed(1) : Math.round(v).toString());

const nodeTypes = { svc: ServiceNode };

export default function ServiceGraph({ services }: { services: Record<string, ServiceState> }) {
  const nodes: Node<SvcData>[] = useMemo(
    () =>
      Object.entries(POS).map(([id, position]) => ({
        id, position, type: "svc", data: { name: id, svc: services[id] }, draggable: false,
      })),
    [services],
  );
  const edges: Edge[] = useMemo(
    () =>
      EDGES.map(([s, t]) => {
        const bad = services[t]?.health === "red";
        return {
          id: `${s}-${t}`, source: s, target: t, animated: bad,
          style: { stroke: bad ? "#ef4444" : "#475569", strokeWidth: 2 },
        };
      }),
    [services],
  );
  return (
    <div className="h-[330px] w-full">
      <ReactFlow nodes={nodes} edges={edges} nodeTypes={nodeTypes} fitView fitViewOptions={{ padding: 0.12 }}
        proOptions={{ hideAttribution: true }} nodesConnectable={false} elementsSelectable={false}
        panOnDrag={false} zoomOnScroll={false} zoomOnDoubleClick={false} preventScrolling={false}>
        <Background color="#1e293b" gap={18} />
      </ReactFlow>
    </div>
  );
}
