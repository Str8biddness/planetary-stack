// learning/trainChatAttention.ts
// Training runner for Chat Attention organ

import { buildChatAttentionDataset } from './chat/attentionData';
import { ChatAttentionModel } from '../organs/chat/ChatAttentionModel';
import { ChatAttentionOrgan } from '../organs/chat/ChatAttentionOrgan';
import { OrganRegistry, OrganType } from '../organs/registry';
import { organMonitor } from './monitoring';

export async function trainChatAttention() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  const { inputs, targets } = await buildChatAttentionDataset(from, to);
  if (inputs.length === 0) {
    console.log('No training data found for Chat Attention. Skipping.');
    return;
  }

  const model = new ChatAttentionModel();
  model.train(inputs, targets);

  // Evaluate MSE
  const preds = inputs.map(i => model.score(i));
  const mse = preds.reduce((sum, p, idx) => sum + p.reduce((s, v, j) => s + (v - targets[idx][j]) ** 2, 0) / p.length, 0) / preds.length;
  const baseline = 0; // uniform
  const baselineMse = targets.reduce((sum, t) => sum + t.reduce((s, v) => s + v ** 2, 0) / t.length, 0) / targets.length;

  const domain = 'chat';
  const organType = 'Attention';
  organMonitor.recordMetrics(domain, organType, 'new', mse);

  if (organMonitor.shouldRevert(domain, organType, mse)) {
    const lastGoodVersion = organMonitor.getLastGoodVersion(domain, organType);
    if (lastGoodVersion) {
      console.log(`Reverting to last good version ${lastGoodVersion}`);
      OrganRegistry.setCurrentVersion(OrganType.Attention, 'chat', lastGoodVersion);
    }
  } else if (mse < baselineMse) {
    const params = model.toJSON();
    const organ = new ChatAttentionOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.Attention, 'chat', organ.version);
    console.log(`Trained new version, MSE ${mse} < baseline ${baselineMse}`);
  } else {
    console.log(`Training failed, MSE ${mse} >= baseline ${baselineMse}`);
  }
}
