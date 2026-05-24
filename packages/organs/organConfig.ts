// organs/organConfig.ts
// Thresholds and configuration for all Synthesus ML organs

import { OrganType } from './registry';

export interface OrganThresholds {
  maxAccuracyDrop?: number;
  maxMseIncrease?: number;
  maxKlIncrease?: number;
}

export interface OrganConfig {
  type: OrganType;
  domain: 'gm' | 'sysops' | 'chat' | 'default';
  thresholds: OrganThresholds;
}

export const organConfigs: OrganConfig[] = [
  // GM
  { type: OrganType.PolicyPrior, domain: 'gm', thresholds: { maxAccuracyDrop: 0.05 } },
  { type: OrganType.RiskOutcome, domain: 'gm', thresholds: { maxMseIncrease: 0.1 } },
  { type: OrganType.Attention, domain: 'gm', thresholds: { maxMseIncrease: 0.05 } },
  // SysOps
  { type: OrganType.PolicyPrior, domain: 'sysops', thresholds: { maxAccuracyDrop: 0.05 } },
  { type: OrganType.RiskOutcome, domain: 'sysops', thresholds: { maxMseIncrease: 0.1 } },
  { type: OrganType.Attention, domain: 'sysops', thresholds: { maxMseIncrease: 0.05 } },
  // Chat
  { type: OrganType.PolicyPrior, domain: 'chat', thresholds: { maxAccuracyDrop: 0.05 } },
  { type: OrganType.RiskOutcome, domain: 'chat', thresholds: { maxMseIncrease: 0.1 } },
  { type: OrganType.Attention, domain: 'chat', thresholds: { maxMseIncrease: 0.05 } },
  // Default/shared organs
  { type: OrganType.Prediction, domain: 'default', thresholds: { maxMseIncrease: 0.08 } },
  { type: OrganType.Forecast, domain: 'default', thresholds: { maxMseIncrease: 0.08 } },
  { type: OrganType.SequencePrediction, domain: 'default', thresholds: { maxMseIncrease: 0.08 } },
  { type: OrganType.Relation, domain: 'default', thresholds: { maxMseIncrease: 0.08 } },
  { type: OrganType.AnomalyEvent, domain: 'default', thresholds: { maxMseIncrease: 0.08 } },
  { type: OrganType.Summarizer, domain: 'default', thresholds: { maxMseIncrease: 0.08 } },
];

export function getOrganConfig(domain: string, type: OrganType): OrganConfig | undefined {
  return organConfigs.find(c => c.domain === domain && c.type === type);
}
