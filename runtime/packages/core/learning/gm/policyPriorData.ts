// learning/gm/policyPriorData.ts
// Builds training dataset for GM PolicyPrior organ from Teacher/Trace logs

import { StateFeatures, ActionFeatures } from '../../amplification/features';
import { loadEntries, PlanningTraceEntry } from '../teacherTrace';

export async function buildGmPolicyPriorDataset(from: Date, to: Date): Promise<{ inputs: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }[]; targets: number[][] }> {
  const planningLogs: PlanningTraceEntry[] = await loadEntries({ domain: 'gm', from, to, phase: 'planning' });

  const inputs: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }[] = [];
  const targets: number[][] = [];

  for (const entry of planningLogs) {
    if (entry.stateFeatures && entry.actionFeatures && entry.organOutputs?.policyScores) {
      inputs.push({ stateFeatures: entry.stateFeatures, actionFeaturesList: entry.actionFeatures });
      targets.push(entry.organOutputs.policyScores as number[]);
    }
  }

  return { inputs, targets };
}
