// organs/sysops/SysRiskOutcomeOrgan.ts
// Heuristic RiskOutcome organ for SysOps domain in Synthesus 3.0

import { Organ, OrganType, OrganContext } from '../registry';
import { TrajectoryFeatures } from '../../core/amplification/features';
import { toNumber } from '../../core/utils/normalization';

import { SysOpsRiskOutcomeModel, SysOpsRiskOutcomeModelParams } from './SysOpsRiskOutcomeModel';

export class SysRiskOutcomeOrgan implements Organ<TrajectoryFeatures, { risk: number; stability: number; drama: number }> {
  type = OrganType.RiskOutcome;
  version = 'v1';
  domain = 'sysops';

  private model?: SysOpsRiskOutcomeModel;

  constructor(params?: SysOpsRiskOutcomeModelParams) {
    this.model = params ? SysOpsRiskOutcomeModel.fromJSON(params) : undefined;
  }

  async predict(input: TrajectoryFeatures, ctx: OrganContext): Promise<{ risk: number; stability: number; drama: number }> {
    const modelRisk = this.model && ctx.computeBudget > 10 ? this.model.score(input) : null;
    
    const incidentRate = toNumber(input.sparse?.incidentRate);
    const stability = toNumber(input.sparse?.stability);
    
    let risk = modelRisk !== null ? modelRisk : 0.5;
    let drama = 0.5;
    
    if (modelRisk === null) {
      if (incidentRate > 0.3) risk += 0.3;
      if (stability < 0.5) risk += 0.2;
    }
    
    if (incidentRate > 0.5) drama += 0.3;
    
    return {
      risk: Math.min(1, risk),
      stability: Math.min(1, stability),
      drama: Math.min(1, drama),
    };
  }

  static loadFromParams(params: SysOpsRiskOutcomeModelParams): SysRiskOutcomeOrgan {
    return new SysRiskOutcomeOrgan(params);
  }

  exportParams(): SysOpsRiskOutcomeModelParams | undefined {
    return this.model?.toJSON();
  }
}
