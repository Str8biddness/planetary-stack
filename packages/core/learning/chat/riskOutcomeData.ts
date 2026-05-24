// learning/chat/riskOutcomeData.ts
// Builds training dataset for Chat RiskOutcome organ from Teacher/Trace logs

import { TrajectoryFeatures } from '../../amplification/features';
import { loadEntries, OutputTraceEntry } from '../teacherTrace';
import { computeWeightedQuality } from '../outcomeConfig';

export async function buildChatRiskOutcomeDataset(from: Date, to: Date): Promise<{ inputs: TrajectoryFeatures[]; targets: number[] }> {
  const outputLogs: OutputTraceEntry[] = await loadEntries({ domain: 'chat', from, to, phase: 'output' });

  const inputs: TrajectoryFeatures[] = [];
  const targets: number[] = [];

  for (const entry of outputLogs) {
    if (entry.trajectoryFeatures && entry.outcome) {
      const metrics = entry.outcome.metrics || {
        clarity: (entry.outcome.clarity as number) || 0.5,
        resolution: (entry.outcome.resolution as number) || 0.5,
        safety: (entry.outcome.safety as number) || 1.0,
      };
      const quality = computeWeightedQuality('chat', metrics);
      inputs.push(entry.trajectoryFeatures);
      targets.push(quality);
    }
  }

  return { inputs, targets };
}
