// Mirrors shared/types.py (Message is what every bus event looks like).

export type MsgType =
  | "telemetry" | "belief" | "evidence" | "challenge" | "proposal" | "accept" | "reject"
  | "veto" | "escalate" | "human_response" | "action" | "mode_switch" | "recruit";

export interface Msg {
  id: number;
  run_id: string;
  tick: number;
  sender: string;
  type: MsgType;
  content: Record<string, any>;
  rationale: string;
}

export interface AgentSpec {
  id: string;
  name: string;
  role: string;
  goal: string;
  features: string[];
  capabilities: string[];
  core: boolean;
  safety_critical: boolean;
  color: string;
}

export type Health = "green" | "yellow" | "red";

export interface ServiceState {
  health: Health;
  levels: Record<string, string>;
  values: Record<string, number>;
}

export interface Option {
  action: string;
  hypothesis: string | null;
  probability: number | null;
  risk: string;
  blocked_without_approval: boolean;
}

export interface Metrics {
  scenario: string;
  mode: string;
  seed: number;
  true_fault: string;
  recovery_time: number;
  availability: number;
  unnecessary_actions: number;
  correct_diagnosis: boolean;
  escalated_to_human: boolean;
  brier_score: number | null;
  llm_calls: number;
}

export const HYPOTHESES = ["bad_deploy", "attack", "db_fault", "dependency_timeout"] as const;

export const HYP_COLOR: Record<string, string> = {
  bad_deploy: "#a855f7",
  attack: "#ef4444",
  db_fault: "#f59e0b",
  dependency_timeout: "#06b6d4",
};

export const SYSTEM_COLOR: Record<string, string> = {
  router: "#94a3b8",
  runbook: "#64748b",
  aggregator: "#e2e8f0",
  validator: "#f97316",
  human: "#22c55e",
  team: "#e2e8f0",
  system: "#475569",
  simulator: "#475569",
};
