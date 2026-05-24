// learning/gm/attentionData.ts
// Builds training dataset for GM Attention organ from Teacher/Trace logs

import { MultiFocusFeatures } from '../../amplification/features';
import { loadEntries, PlanningTraceEntry } from '../teacherTrace';

export async function buildGmAttentionDataset(from: Date, to: Date): Promise<{ inputs: MultiFocusFeatures[]; targets: number[][] }> {
  const planningLogs: PlanningTraceEntry[] = await loadEntries({ domain: 'gm', from, to, phase: 'planning' });

  const inputs: MultiFocusFeatures[] = [];
  const targets: number[][] = [];

  for (const entry of planningLogs) {
    if (entry.multiFocusFeatures && entry.organOutputs?.attentionWeights) {
      inputs.push(entry.multiFocusFeatures);
      targets.push(entry.organOutputs.attentionWeights as number[]);
    }
  }

  return { inputs, targets };
}
