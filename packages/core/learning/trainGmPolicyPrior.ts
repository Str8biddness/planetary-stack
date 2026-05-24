// learning/trainGmPolicyPrior.ts
// Training runner for GM PolicyPrior organ

import { buildGmPolicyPriorDataset } from './gm/policyPriorData';
import { GmPolicyPriorModel } from '../organs/gm/GmPolicyPriorModel';
import { GmPolicyPriorOrgan } from '../organs/gm/GmPolicyPriorOrgan';
import { OrganRegistry, OrganType } from '../organs/registry';
import { organMonitor } from './monitoring';

export async function trainGmPolicyPrior() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  const { inputs, targets } = await buildGmPolicyPriorDataset(from, to);

  const model = new GmPolicyPriorModel();
  model.train(inputs, targets);

  // Evaluate average MSE
  let totalMse = 0;
  for (let i = 0; i < inputs.length; i++) {
    const pred = model.score(inputs[i]);
    const target = targets[i];
    const mse = pred.reduce((sum, p, idx) => sum + (p - target[idx]) ** 2, 0) / pred.length;
    totalMse += mse;
  }
  const avgMse = totalMse / inputs.length;

  // Baseline: uniform 0.5
  const baselineMse = targets.reduce((sum, t) => sum + t.reduce((s, v) => s + (0.5 - v) ** 2, 0) / t.length, 0) / targets.length;

  const domain = 'gm';
  const organType = 'PolicyPrior';
  organMonitor.recordMetrics(domain, organType, 'new', avgMse);

  if (organMonitor.shouldRevert(domain, organType, avgMse)) {
    const lastGoodVersion = organMonitor.getLastGoodVersion(domain, organType);
    if (lastGoodVersion) {
      console.log(`Reverting to last good version ${lastGoodVersion}`);
      OrganRegistry.setCurrentVersion(OrganType.PolicyPrior, 'gm', lastGoodVersion);
    }
  } else if (avgMse < baselineMse) {
    const params = model.toJSON();
    const organ = new GmPolicyPriorOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.PolicyPrior, 'gm', organ.version);
    console.log(`Trained new version, MSE ${avgMse} < baseline ${baselineMse}`);
  } else {
    console.log(`Training failed, MSE ${avgMse} >= baseline ${baselineMse}`);
  }
}
