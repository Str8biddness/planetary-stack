// organs/registry.ts
// Registry for ML organs with versioning for Synthesus 3.0

export enum OrganType {
  PolicyPrior = 'policy_prior',
  RiskOutcome = 'risk_outcome',
  Attention = 'attention',
  Prediction = 'prediction',
  Forecast = 'forecast',
  SequencePrediction = 'sequence_prediction',
  Relation = 'relation',
  Memory = 'memory',
  AnomalyEvent = 'anomaly_event',
  Summarizer = 'summarizer'
}

export interface Organ<Input, Output> {
  type: OrganType;
  version: string;
  domain?: string;
  predict(input: Input, ctx: OrganContext): Promise<Output>;
}

export interface OrganContext {
  sessionId: string;
  computeBudget: number;
  [key: string]: any;
}

// Simple in-memory registry with versioning
export class OrganRegistry {
  private static organs: Map<string, Organ<any, any>> = new Map();
  private static currentVersions: Map<string, string> = new Map();

  static registerOrgan(organ: Organ<any, any>): void {
    const key = `${organ.type}:${organ.domain || 'default'}`;
    this.organs.set(key, organ);
  }

  static getOrgan(type: OrganType, domain?: string): Organ<any, any> | undefined {
    const key = `${type}:${domain || 'default'}`;
    const organ = this.organs.get(key);
    if (organ) return organ;
    const defaultKey = `${type}:default`;
    return this.organs.get(defaultKey);
  }

  static setCurrentVersion(type: OrganType, domain: string, version: string): void {
    const key = `${type}:${domain}`;
    this.currentVersions.set(key, version);
  }

  static getCurrentVersion(type: OrganType, domain: string): string | undefined {
    return this.currentVersions.get(`${type}:${domain}`);
  }
}
