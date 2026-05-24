// learning/sysops/riskOutcomeData.ts
// Builds training dataset for SysOps RiskOutcome organ from Teacher/Trace logs

import { TrajectoryFeatures } from '../../amplification/features';
import { loadEntries, OutputTraceEntry } from '../teacherTrace';
import { computeWeightedQuality } from '../outcomeConfig';

export async function buildSysOpsRiskOutcomeDataset(from: Date, to: Date): Promise<{ inputs: TrajectoryFeatures[]; targets: number[] }> {
  const outputLogs: OutputTraceEntry[] = await loadEntries({ domain: 'sysops', from, to, phase: 'output' });

  const inputs: TrajectoryFeatures[] = [];
  const targets: number[] = [];

  for (const entry of outputLogs) {
    if (entry.trajectoryFeatures && entry.outcome) {
      const metrics = entry.outcome.metrics || {
        stability: (entry.outcome.stability as number) || 0.5,
        sloImpact: (entry.outcome.sloImpact as number) || 0.0,
        safety: (entry.outcome.safety as number) || 1.0,
      };
      const quality = computeWeightedQuality('sysops', metrics);
      inputs.push(entry.trajectoryFeatures);
      targets.push(quality);
    }
  }

  return { inputs, targets };
}
