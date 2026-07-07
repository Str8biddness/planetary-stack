// learning/trainGmRiskOutcome.ts
// Training runner for GM RiskOutcome organ

import { OrganRegistry, OrganType } from '../../organs/registry';
import { GmRiskOutcomeModel } from '../../organs/gm/GmRiskOutcomeModel';
import { GmRiskOutcomeOrgan } from '../../organs/gm/GmRiskOutcomeOrgan';
import { buildGmRiskOutcomeDataset } from './gm/riskOutcomeData';
import { organMonitor } from './monitoring';

export async function trainGmRiskOutcome() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  const { inputs, targets } = await buildGmRiskOutcomeDataset(from, to);

  if (inputs.length === 0) {
    console.log('No training data found for GM RiskOutcome. Skipping.');
    return;
  }

  const model = new GmRiskOutcomeModel();
  model.train(inputs, targets);

  // Evaluate MSE
  const preds = inputs.map(i => model.score(i));
  const mse = preds.reduce((sum, p, idx) => sum + (p - targets[idx]) ** 2, 0) / preds.length;
  const baseline = 0; // naive
  const baselineMse = targets.reduce((sum, t) => sum + t ** 2, 0) / targets.length;

  const domain = 'gm';
  const organType = 'RiskOutcome';
  organMonitor.recordMetrics(domain, organType, 'new', mse);

  if (organMonitor.shouldRevert(domain, organType, mse)) {
    const lastGoodVersion = organMonitor.getLastGoodVersion(domain, organType);
    if (lastGoodVersion) {
      console.log(`Reverting to last good version ${lastGoodVersion}`);
      OrganRegistry.setCurrentVersion(OrganType.RiskOutcome, 'gm', lastGoodVersion);
    }
  } else if (mse < baselineMse) {
    const params = model.toJSON();
    const organ = new GmRiskOutcomeOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.RiskOutcome, 'gm', organ.version);
    console.log(`Trained new version, MSE ${mse} < baseline ${baselineMse}`);
  } else {
    console.log(`Training failed, MSE ${mse} >= baseline ${baselineMse}`);
  }
}
