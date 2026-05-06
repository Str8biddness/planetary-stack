// learning/trainSysOpsPolicyPrior.ts
// Training runner for SysOps PolicyPrior organ

import { OrganRegistry, OrganType } from '../organs/registry';
import { SysOpsPolicyPriorModel as SysPolicyPriorModel } from '../organs/sysops/SysOpsPolicyPriorModel';
import { SysPolicyPriorOrgan } from '../organs/sysops/SysPolicyPriorOrgan';
import { buildSysOpsPolicyPriorDataset as buildSysPolicyPriorDataset } from './sysops/policyPriorData';

export async function trainSysOpsPolicyPrior() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  
  console.log('Building SysOps PolicyPrior dataset...');
  const { inputs, targets } = await buildSysPolicyPriorDataset(from, to);
  
  if (inputs.length === 0) {
    console.log('No training data found for SysOps PolicyPrior. Skipping.');
    return;
  }

  const model = new SysPolicyPriorModel();
  model.train(inputs, targets);

  // Evaluate accuracy by comparing predicted best index vs target best index
  let correct = 0;
  for (let i = 0; i < inputs.length; i++) {
    const pred = model.score(inputs[i]);
    const bestPredIdx = pred.indexOf(Math.max(...pred));
    const bestTargetIdx = targets[i].indexOf(Math.max(...targets[i]));
    if (bestPredIdx === bestTargetIdx) {
      correct++;
    }
  }
  const accuracy = correct / inputs.length;
  const baselineAccuracy = inputs.length > 0 ? 1 / inputs[0].actionFeaturesList.length : 0;

  if (accuracy > baselineAccuracy) {
    const params = model.toJSON();
    const organ = new SysPolicyPriorOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.PolicyPrior, 'sysops', organ.version);
    console.log(`Trained new version, accuracy ${accuracy} > baseline ${baselineAccuracy}`);
  } else {
    console.log(`Training failed, accuracy ${accuracy} <= baseline ${baselineAccuracy}`);
  }
}
