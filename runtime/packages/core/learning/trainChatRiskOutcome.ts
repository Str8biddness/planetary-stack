// learning/trainChatRiskOutcome.ts
// Training runner for Chat RiskOutcome organ

import { buildChatRiskOutcomeDataset } from './chat/riskOutcomeData';
import { ChatRiskOutcomeModel } from '../../organs/chat/ChatRiskOutcomeModel';
import { ChatRiskOutcomeOrgan } from '../../organs/chat/ChatRiskOutcomeOrgan';
import { OrganRegistry, OrganType } from '../../organs/registry';
import { organMonitor } from './monitoring';

export async function trainChatRiskOutcome() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  const { inputs, targets } = await buildChatRiskOutcomeDataset(from, to);
  if (inputs.length === 0) {
    console.log('No training data found for Chat RiskOutcome. Skipping.');
    return;
  }

  const model = new ChatRiskOutcomeModel();
  model.train(inputs, targets);

  // Evaluate MSE
  const preds = inputs.map(i => model.score(i));
  const mse = preds.reduce((sum, p, idx) => sum + (p - targets[idx]) ** 2, 0) / preds.length;
  const baselineMse = targets.reduce((sum, t) => sum + t ** 2, 0) / targets.length;

  const domain = 'chat';
  const organType = 'RiskOutcome';
  
  // Use monitoring if available
  const { organMonitor } = await import('./monitoring');
  organMonitor.recordMetrics(domain, organType, 'new', mse);

  if (organMonitor.shouldRevert(domain, organType, mse)) {
    const lastGoodVersion = organMonitor.getLastGoodVersion(domain, organType);
    if (lastGoodVersion) {
      console.log(`Reverting ${domain} ${organType} to last good version ${lastGoodVersion}`);
      OrganRegistry.setCurrentVersion(OrganType.RiskOutcome, domain, lastGoodVersion);
      return;
    }
  }

  if (mse < baselineMse) {
    const params = model.toJSON();
    const organ = new ChatRiskOutcomeOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.RiskOutcome, 'chat', organ.version);
    console.log(`Trained new version, MSE ${mse} < baseline ${baselineMse}`);
  } else {
    console.log(`Training failed, MSE ${mse} >= baseline ${baselineMse}`);
  }
}
