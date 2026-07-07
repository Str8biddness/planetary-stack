// learning/trainGmAttention.ts
// Training runner for GM Attention organ

import { buildGmAttentionDataset } from './gm/attentionData';
import { GmAttentionModel } from '../../organs/gm/GmAttentionModel';
import { GmAttentionOrgan } from '../../organs/gm/GmAttentionOrgan';
import { OrganRegistry, OrganType } from '../../organs/registry';
import { organMonitor } from './monitoring';

export async function trainGmAttention() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  const { inputs, targets } = await buildGmAttentionDataset(from, to);

  if (inputs.length === 0) {
    console.log('No training data found for GM Attention. Skipping.');
    return;
  }

  const model = new GmAttentionModel();
  model.train(inputs, targets);

  // Evaluate MSE
  const preds = inputs.map(i => model.score(i));
  const mse = preds.reduce((sum, p, idx) => sum + p.reduce((s, v, j) => s + (v - targets[idx][j]) ** 2, 0) / p.length, 0) / preds.length;
  const baselineMse = targets.reduce((sum, t) => sum + t.reduce((s, v) => s + v ** 2, 0) / t.length, 0) / targets.length;

  const domain = 'gm';
  const organType = 'Attention';
  organMonitor.recordMetrics(domain, organType, 'new', mse);

  if (organMonitor.shouldRevert(domain, organType, mse)) {
    const lastGoodVersion = organMonitor.getLastGoodVersion(domain, organType);
    if (lastGoodVersion) {
      console.log(`Reverting to last good version ${lastGoodVersion}`);
      OrganRegistry.setCurrentVersion(OrganType.Attention, 'gm', lastGoodVersion);
    }
  } else if (mse < baselineMse) {
    const params = model.toJSON();
    const organ = new GmAttentionOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.Attention, 'gm', organ.version);
    console.log(`Trained new version, MSE ${mse} < baseline ${baselineMse}`);
  } else {
    console.log(`Training failed, MSE ${mse} >= baseline ${baselineMse}`);
  }
}
