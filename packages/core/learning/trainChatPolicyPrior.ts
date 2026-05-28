// learning/trainChatPolicyPrior.ts
// Training runner for Chat PolicyPrior organ

import { buildChatPolicyPriorDataset } from './chat/policyPriorData';
import { ChatPolicyPriorModel } from '../../organs/chat/ChatPolicyPriorModel';
import { ChatPolicyPriorOrgan } from '../../organs/chat/ChatPolicyPriorOrgan';
import { OrganRegistry, OrganType } from '../../organs/registry';
import { organMonitor } from './monitoring';

export async function trainChatPolicyPrior() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  const { inputs, targets } = await buildChatPolicyPriorDataset(from, to);

  if (inputs.length === 0) {
    console.log('No training data found for Chat PolicyPrior. Skipping.');
    return;
  }

  const model = new ChatPolicyPriorModel();
  model.train(inputs, targets, { epochs: 10, learningRate: 0.01 });

  // Evaluate: fraction of cases where argmax(scores) === chosenIndex
  let correct = 0;
  for (let i = 0; i < inputs.length; i++) {
    const scores = model.score(inputs[i].stateFeatures, inputs[i].actionFeaturesList);
    const predicted = scores.indexOf(Math.max(...scores));
    if (predicted === targets[i].chosenIndex) {
      correct++;
    }
  }
  const accuracy = correct / inputs.length;

  // Baseline: uniform random accuracy = 1 / avg_num_actions
  const avgActions = inputs.reduce((s, inp) => s + inp.actionFeaturesList.length, 0) / inputs.length;
  const baselineAccuracy = 1 / Math.max(avgActions, 1);

  const domain = 'chat';
  const organType = 'PolicyPrior';
  // Record 1-accuracy as "mse" for the monitor (lower is better)
  const metric = 1 - accuracy;
  organMonitor.recordMetrics(domain, organType, 'new', metric);

  if (organMonitor.shouldRevert(domain, organType, metric)) {
    const lastGoodVersion = organMonitor.getLastGoodVersion(domain, organType);
    if (lastGoodVersion) {
      console.log(`Reverting to last good version ${lastGoodVersion}`);
      OrganRegistry.setCurrentVersion(OrganType.PolicyPrior, 'chat', lastGoodVersion);
    }
  } else if (accuracy > baselineAccuracy) {
    const params = model.toJSON();
    const organ = new ChatPolicyPriorOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.PolicyPrior, 'chat', organ.version);
    console.log(`Trained new version — accuracy ${(accuracy * 100).toFixed(1)}% > baseline ${(baselineAccuracy * 100).toFixed(1)}%`);
  } else {
    console.log(`Training did not beat baseline — accuracy ${(accuracy * 100).toFixed(1)}% <= baseline ${(baselineAccuracy * 100).toFixed(1)}%`);
  }
}
