// learning/trainSysOpsAttention.ts
// Training runner for SysOps Attention organ

import { OrganRegistry, OrganType } from '../../organs/registry';
import { SysOpsAttentionModel } from '../../organs/sysops/SysOpsAttentionModel';
import { SysAttentionOrgan } from '../../organs/sysops/SysAttentionOrgan';
import { buildSysOpsAttentionDataset } from './sysops/attentionData';

export async function trainSysOpsAttention() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  
  console.log('Building SysOps Attention dataset...');
  const { inputs, targets } = await buildSysOpsAttentionDataset(from, to);
  
  if (inputs.length === 0) {
    console.log('No training data found for SysOps Attention. Skipping.');
    return;
  }

  const model = new SysOpsAttentionModel();
  model.train(inputs, targets);

  // Evaluate MSE
  let totalMse = 0;
  for (let i = 0; i < inputs.length; i++) {
    const pred = model.score(inputs[i]);
    const target = targets[i];
    const mse = pred.reduce((sum, p, idx) => sum + (p - target[idx]) ** 2, 0) / pred.length;
    totalMse += mse;
  }
  const avgMse = totalMse / inputs.length;
  
  // Naive baseline: uniform weights
  const baselineMse = targets.reduce((sum, t) => {
    const uniform = Array(t.length).fill(1 / t.length);
    return sum + t.reduce((s, v, idx) => s + (v - uniform[idx]) ** 2, 0) / t.length;
  }, 0) / targets.length;

  if (avgMse < baselineMse) {
    const params = model.toJSON();
    const organ = new SysAttentionOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.Attention, 'sysops', organ.version);
    console.log(`Trained new version, MSE ${avgMse} < baseline ${baselineMse}`);
  } else {
    console.log(`Training failed, MSE ${avgMse} >= baseline ${baselineMse}`);
  }
}
