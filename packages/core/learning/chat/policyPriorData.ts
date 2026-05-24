// learning/chat/policyPriorData.ts
// Builds training dataset for Chat PolicyPrior organ from Teacher/Trace logs

import { StateFeatures, ActionFeatures } from '../../amplification/features';
import { loadEntries, PlanningTraceEntry } from '../teacherTrace';

export interface ChatPolicyPriorInput {
  stateFeatures: StateFeatures;
  actionFeaturesList: ActionFeatures[];
}

export interface ChatPolicyPriorTarget {
  chosenIndex: number;      // index of the action actually taken
  quality: number;          // scalar quality score (e.g., outcome.quality)
}

export async function buildChatPolicyPriorDataset(
  from?: Date,
  to?: Date
): Promise<{ inputs: ChatPolicyPriorInput[]; targets: ChatPolicyPriorTarget[] }> {
  const planningLogs: PlanningTraceEntry[] = await loadEntries({
    domain: 'chat',
    from,
    to,
    phase: 'planning',
  });

  const inputs: ChatPolicyPriorInput[] = [];
  const targets: ChatPolicyPriorTarget[] = [];

  for (const entry of planningLogs) {
    if (!entry.stateFeatures || !entry.actionFeatures || entry.actionFeatures.length === 0) {
      continue;
    }

    const chosenIndex = entry.chosenActionIndex ?? 0;
    const quality = entry.outcome?.quality ?? 1;

    inputs.push({
      stateFeatures: entry.stateFeatures,
      actionFeaturesList: entry.actionFeatures,
    });

    targets.push({ chosenIndex, quality });
  }

  return { inputs, targets };
}
