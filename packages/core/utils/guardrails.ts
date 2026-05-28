// utils/guardrails.ts

import { AutonomyLevel, GLOBAL_KILL_SWITCH, getDomainConfig } from '../../organs/autonomyConfig';

export enum ExecutionRecommendation {
  EXECUTE = 'execute',
  REQUEST_CONFIRMATION = 'request_confirmation',
  REJECT = 'reject'
}

export interface TriadGatingInput {
  riskScore: number;
  confidenceMargin: number; // e.g., (top1 - top2) score
  attentionSensitivity: number; // 0-1 (1 is highly sensitive)
}

export function enforceAutonomy(
  domain: string,
  actionType: string,
  triadOutput: TriadGatingInput
): ExecutionRecommendation {
  const config = getDomainConfig(domain);

  // 1. Kill Switch
  if (GLOBAL_KILL_SWITCH) {
    return ExecutionRecommendation.REQUEST_CONFIRMATION; // Fallback to advisor/copilot behavior
  }

  // 2. Allowed Tools Check
  if (!config.allowedTools.includes(actionType)) {
    return ExecutionRecommendation.REQUEST_CONFIRMATION;
  }

  // 3. Level Enforcement
  if (config.level === AutonomyLevel.ADVISOR) {
    return ExecutionRecommendation.REQUEST_CONFIRMATION;
  }

  if (config.level === AutonomyLevel.COPILOT) {
    return ExecutionRecommendation.REQUEST_CONFIRMATION;
  }

  // 4. Autopilot (Level 3) Bounded Checks
  if (config.level === AutonomyLevel.AUTOPILOT) {
    // Check RiskOutcome (lower risk is better, but here we assume high score is high quality/safety)
    // Actually, in our V3 logic, higher RiskOutcome often means higher quality.
    // Let's assume triadOutput.riskScore is a safety/quality signal (0-1).
    if (triadOutput.riskScore < config.maxRiskThreshold) {
      return ExecutionRecommendation.REQUEST_CONFIRMATION;
    }

    // Check PolicyPrior confidence
    if (triadOutput.confidenceMargin < config.minConfidenceThreshold) {
      return ExecutionRecommendation.REQUEST_CONFIRMATION;
    }

    // Check Attention sensitivity
    if (triadOutput.attentionSensitivity > 0.5) {
       return ExecutionRecommendation.REQUEST_CONFIRMATION;
    }

    return ExecutionRecommendation.EXECUTE;
  }

  return ExecutionRecommendation.REQUEST_CONFIRMATION;
}
