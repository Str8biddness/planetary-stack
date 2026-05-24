// organs/sysops/SysPolicyPriorOrgan.ts
// Heuristic PolicyPrior organ for SysOps domain in Synthesus 3.0

import { Organ, OrganType, OrganContext } from '../registry';
import { StateFeatures, ActionFeatures } from '../../amplification/features';
import { toNumber } from '../../utils/normalization';

import { SysOpsPolicyPriorModel, SysOpsPolicyPriorModelParams } from './SysOpsPolicyPriorModel';

export class SysPolicyPriorOrgan implements Organ<{ stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }, { scores: number[] }> {
  type = OrganType.PolicyPrior;
  version = 'v1';
  domain = 'sysops';

  private model?: SysOpsPolicyPriorModel;

  constructor(params?: SysOpsPolicyPriorModelParams) {
    if (params) {
      this.model = new SysOpsPolicyPriorModel(params);
    }
  }

  async predict(input: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }, ctx: OrganContext): Promise<{ scores: number[] }> {
    if (this.model && ctx.computeBudget > 10) {
      const scores = this.model.score(input);
      return { scores };
    }

    const { actionFeaturesList } = input;
    const scores = actionFeaturesList.map(action => {
      let score = 0.5;
      const targetHealth = toNumber(action.sparse?.targetHealth);
      const incidentCount = toNumber(action.sparse?.incidentCount);
      if (targetHealth < 0.3) score += 0.3;
      if (toNumber(action.dense?.[0]) === 1 || toNumber(action.dense?.[1]) === 1) score += 0.2;
      if (incidentCount > 2) score -= 0.2;
      return Math.max(0, Math.min(1, score));
    });
    return { scores };
  }

  static loadFromParams(params: SysOpsPolicyPriorModelParams): SysPolicyPriorOrgan {
    return new SysPolicyPriorOrgan(params);
  }

  exportParams(): SysOpsPolicyPriorModelParams | undefined {
    return this.model?.toJSON();
  }
}
