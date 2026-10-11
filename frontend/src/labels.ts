// Plain-English names for everything a judge sees. One place, so wording stays consistent.

export const SCENARIOS: Record<string, { name: string; blurb: string }> = {
  S1: { name: "Database failure (clear-cut)", blurb: "An obvious database fault. The fixed rule should handle this well." },
  S2: { name: "Bad release disguised as an attack", blurb: "A faulty software release that, on some runs, looks like hacking." },
  S3: { name: "Slow downstream service", blurb: "A dependency times out; a specialist agent is called in mid-incident." },
  S5: { name: "Ambiguous and risky", blurb: "Evidence is split and every fix is risky. The right move is to ask a human." },
};

export const MODES: Record<string, { name: string; blurb: string }> = {
  A: { name: "Fixed rule (baseline)", blurb: "A traditional if-then runbook. No AI." },
  B: { name: "Agents + coordinator", blurb: "Agents share what they believe; one coordinator makes the call." },
  C: { name: "Agents negotiate (our approach)", blurb: "Agents challenge each other and vote. No boss; safety agents can veto." },
  D: { name: "Fixed rule first, then agents", blurb: "The runbook tries first; agents take over if it fails, can't decide, or two rules disagree." },
};

export const HYPOTHESIS: Record<string, string> = {
  bad_deploy: "Bad release",
  attack: "Attack",
  db_fault: "Database fault",
  dependency_timeout: "Slow dependency",
};

export const ACTION: Record<string, string> = {
  rollback_deploy: "Roll back the release",
  block_traffic: "Block suspicious traffic",
  failover_db: "Switch to the backup database",
  restart_service: "Restart the slow service",
  probe: "Take a closer look (probe)",
  noop: "Wait",
};

// Friendly names for message types (ledger tags).
export const TYPE_LABEL: Record<string, string> = {
  telemetry: "System",
  belief: "Thinks",
  evidence: "Shares data",
  challenge: "Challenges",
  proposal: "Proposes",
  accept: "Agrees",
  reject: "Disagrees",
  veto: "Vetoes",
  escalate: "Asks a human",
  human_response: "Human decides",
  action: "Acts",
  mode_switch: "Status",
  recruit: "Joins the incident",
};

export const SENDER_NAME: Record<string, string> = {
  router: "Router",
  runbook: "Fixed rule",
  aggregator: "Coordinator",
  validator: "Safety check",
  human: "Human",
  team: "Agent team",
  system: "System",
  simulator: "Simulator",
};

export const hyp = (h?: string | null) => (h ? HYPOTHESIS[h] ?? h : "-");
export const act = (a?: string | null) => (a ? ACTION[a] ?? a : "-");
