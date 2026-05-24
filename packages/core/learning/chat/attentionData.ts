// learning/chat/attentionData.ts
// Builds training dataset for Chat Attention organ from Teacher/Trace logs

import { MultiFocusFeatures } from '../../amplification/features';
import { loadEntries, PlanningTraceEntry } from '../teacherTrace';

// Input: MultiFocusFeatures
// Target: normalized attention weight vector (sums to 1)
export async function buildChatAttentionDataset(from: Date, to: Date): Promise<{ inputs: MultiFocusFeatures[]; targets: number[][] }> {
  const planningLogs: PlanningTraceEntry[] = await loadEntries({ domain: 'chat', from, to, phase: 'planning' });

  const inputs: MultiFocusFeatures[] = [];
  const targets: number[][] = [];

  for (const entry of planningLogs) {
    if (entry.organOutputs?.attentionWeights && entry.outcome?.quality !== undefined) {
      // Assume organOutputs.attentionWeights is an array matching entry.multiFocusFeatures.targets
      const rawWeights = entry.organOutputs.attentionWeights as number[];
      const outcomeQuality = entry.outcome.quality; // scalar, higher is better
      // Boost weights for targets that got focus and had good outcomes
      const boostedWeights = rawWeights.map((w, idx) => {
        const boost = outcomeQuality > 0 ? w * (1 + outcomeQuality) : w;
        return boost;
      });
      // Normalize to sum to 1
      const sum = boostedWeights.reduce((s, v) => s + v, 0);
      const normalized = sum > 0 ? boostedWeights.map(v => v / sum) : boostedWeights.map(() => 1 / boostedWeights.length);
      // We need the original MultiFocusFeatures from entry; assume stored in entry.multiFocusFeatures
      if (entry.multiFocusFeatures) {
        inputs.push(entry.multiFocusFeatures);
        targets.push(normalized);
      }
    }
  }

  return { inputs, targets };
}
