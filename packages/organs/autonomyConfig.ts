// organs/autonomyConfig.ts

export enum AutonomyLevel {
  ADVISOR = 1,   // Observe, analyze, simulate, propose (no execution)
  COPILOT = 2,   // Draft actions, execute only after human confirmation
  AUTOPILOT = 3  // Bounded autonomy: execute within guardrails
}

export interface AutonomySettings {
  level: AutonomyLevel;
  allowedTools: string[];
  maxRiskThreshold: number;       // Max risk allowed for auto-execution
  minConfidenceThreshold: number; // Min PolicyPrior confidence margin
}

// Global safety state
export let GLOBAL_KILL_SWITCH = false;

export function setKillSwitch(active: boolean) {
  GLOBAL_KILL_SWITCH = active;
}

export const AUTO_CONFIG: Record<string, AutonomySettings> = {
  gm: {
    level: AutonomyLevel.COPILOT,
    allowedTools: ['move_character', 'tick_world', 'spawn_npc'],
    maxRiskThreshold: 0.3,
    minConfidenceThreshold: 0.7
  },
  sysops: {
    level: AutonomyLevel.ADVISOR,
    allowedTools: ['runbook_step', 'restart_service'],
    maxRiskThreshold: 0.1, // Very strict for SysOps
    minConfidenceThreshold: 0.9
  },
  chat: {
    level: AutonomyLevel.COPILOT,
    allowedTools: ['open_url', 'call_api', 'summarize_history'],
    maxRiskThreshold: 0.4,
    minConfidenceThreshold: 0.6
  }
};

export function getDomainConfig(domain: string): AutonomySettings {
  return AUTO_CONFIG[domain] || {
    level: AutonomyLevel.ADVISOR,
    allowedTools: [],
    maxRiskThreshold: 0,
    minConfidenceThreshold: 1.0
  };
}
