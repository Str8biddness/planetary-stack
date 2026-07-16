// learning/outcomeConfig.ts
// Per-domain outcome/quality weighting configuration for Synthesus 3.0

export interface OutcomeWeights {
  coherence?: number;
  tension?: number;
  engagement?: number;
  resolution?: number;
  stability?: number;
  sloImpact?: number;
  safety?: number;
  clarity?: number;
}

export interface DomainOutcomeConfig {
  domain: 'gm' | 'sysops' | 'chat';
  weights: OutcomeWeights;
}

export const outcomeConfigs: DomainOutcomeConfig[] = [
  {
    domain: 'gm',
    weights: {
      coherence: 0.4,
      tension: 0.4,
      engagement: 0.2,
    },
  },
  {
    domain: 'sysops',
    weights: {
      stability: 0.5,
      sloImpact: 0.4,
      safety: 0.1,
    },
  },
  {
    domain: 'chat',
    weights: {
      clarity: 0.5,
      resolution: 0.3,
      safety: 0.2,
    },
  },
];

/**
 * Look up the outcome config for a given domain.
 */
export function getOutcomeConfig(domain: string): DomainOutcomeConfig | undefined {
  return outcomeConfigs.find(c => c.domain === domain);
}

/**
 * Compute a weighted quality scalar from raw outcome signals and the domain config.
 * Raw signals are a record of metric name → value (0–1). Missing metrics are ignored.
 * Returns a 0–1 scalar (clamped).
 */
export function computeWeightedQuality(
  domain: string,
  rawSignals: Record<string, number>
): number {
  const config = getOutcomeConfig(domain);
  if (!config) return rawSignals.quality ?? 0.5;

  let weighted = 0;
  let totalWeight = 0;
  for (const [key, weight] of Object.entries(config.weights)) {
    if (weight !== undefined && rawSignals[key] !== undefined) {
      weighted += weight * rawSignals[key];
      totalWeight += weight;
    }
  }
  if (totalWeight === 0) return rawSignals.quality ?? 0.5;
  return Math.max(0, Math.min(1, weighted / totalWeight));
}
