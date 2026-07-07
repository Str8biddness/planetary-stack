// learning/gm/riskOutcomeData.ts
// Builds training dataset for GM RiskOutcome organ from Teacher/Trace logs

import { TrajectoryFeatures } from '../../amplification/features';
import { loadEntries, OutputTraceEntry } from '../teacherTrace';
import { computeWeightedQuality } from '../outcomeConfig';

export async function buildGmRiskOutcomeDataset(from: Date, to: Date): Promise<{ inputs: TrajectoryFeatures[]; targets: number[] }> {
  const outputLogs: OutputTraceEntry[] = await loadEntries({ domain: 'gm', from, to, phase: 'output' });

  const inputs: TrajectoryFeatures[] = [];
  const targets: number[] = [];

  for (const entry of outputLogs) {
    if (entry.trajectoryFeatures && entry.outcome) {
      const metrics = entry.outcome.metrics || {
        coherence: (entry.outcome.coherence as number) || 0.5,
        tension: (entry.outcome.tension as number) || 0.5,
        engagement: (entry.outcome.engagement as number) || 0.5,
      };
      const quality = computeWeightedQuality('gm', metrics);
      inputs.push(entry.trajectoryFeatures);
      targets.push(quality);
    }
  }

  return { inputs, targets };
}
