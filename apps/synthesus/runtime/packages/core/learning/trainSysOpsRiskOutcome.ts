// learning/trainSysOpsRiskOutcome.ts
// Training runner for SysOps RiskOutcome organ

import { OrganRegistry, OrganType } from '../../organs/registry';
import { SysOpsRiskOutcomeModel } from '../../organs/sysops/SysOpsRiskOutcomeModel';
import { SysRiskOutcomeOrgan } from '../../organs/sysops/SysRiskOutcomeOrgan';
import { buildSysOpsRiskOutcomeDataset } from './sysops/riskOutcomeData';

export async function trainSysOpsRiskOutcome() {
  const from = new Date(Date.now() - 7 * 24 * 60 * 60 * 1000);
  const to = new Date();
  
  console.log('Building SysOps RiskOutcome dataset...');
  const { inputs, targets } = await buildSysOpsRiskOutcomeDataset(from, to);
  
  if (inputs.length === 0) {
    console.log('No training data found for SysOps RiskOutcome. Skipping.');
    return;
  }

  const model = new SysOpsRiskOutcomeModel();
  model.train(inputs, targets);

  // Evaluate MSE
  const preds = inputs.map(i => model.score(i));
  const mse = preds.reduce((sum, p, idx) => sum + (p - targets[idx]) ** 2, 0) / preds.length;
  const baselineMse = targets.reduce((sum, t) => sum + t ** 2, 0) / targets.length;

  const domain = 'sysops';
  const organType = 'RiskOutcome';
  
  // Monitoring logic
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
    const organ = new SysRiskOutcomeOrgan(params);
    OrganRegistry.registerOrgan(organ);
    OrganRegistry.setCurrentVersion(OrganType.RiskOutcome, 'sysops', organ.version);
    console.log(`Trained new version, MSE ${mse} < baseline ${baselineMse}`);
  } else {
    console.log(`Training failed, MSE ${mse} >= baseline ${baselineMse}`);
  }
}
