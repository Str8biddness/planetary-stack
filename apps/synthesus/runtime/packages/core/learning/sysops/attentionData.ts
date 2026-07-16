// learning/sysops/attentionData.ts
// Builds training dataset for SysOps Attention organ from Teacher/Trace logs

import { MultiFocusFeatures } from '../../amplification/features';
import { loadEntries, PlanningTraceEntry } from '../teacherTrace';
import { computeWeightedQuality } from '../outcomeConfig';

export async function buildSysOpsAttentionDataset(from: Date, to: Date): Promise<{ inputs: MultiFocusFeatures[]; targets: number[][] }> {
  const planningLogs: PlanningTraceEntry[] = await loadEntries({ domain: 'sysops', from, to, phase: 'planning' });

  const inputs: MultiFocusFeatures[] = [];
  const targets: number[][] = [];

  for (const entry of planningLogs) {
    if (entry.multiFocusFeatures && entry.organOutputs?.attentionWeights && entry.outcome?.quality !== undefined) {
      const metrics = entry.outcome.metrics || {
        stability: (entry.outcome.stability as number) || 0.5,
        sloImpact: (entry.outcome.sloImpact as number) || 0.0,
        safety: (entry.outcome.safety as number) || 1.0,
      };
      const quality = computeWeightedQuality('sysops', metrics);
      const weightedWeights = (entry.organOutputs.attentionWeights as number[]).map(w => w * quality);
      const sum = weightedWeights.reduce((s, v) => s + v, 0);
      const normalizedWeights = sum > 0 ? weightedWeights.map(v => v / sum) : weightedWeights;

      inputs.push(entry.multiFocusFeatures);
      targets.push(normalizedWeights);
    }
  }

  return { inputs, targets };
}
