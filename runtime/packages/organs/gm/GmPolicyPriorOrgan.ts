// organs/gm/GmPolicyPriorOrgan.ts
// GM PolicyPrior organ with model support

import { Organ, OrganType, OrganContext } from '../registry';
import { StateFeatures, ActionFeatures } from '../../core/amplification/features';
import { GmPolicyPriorModel, GmPolicyPriorModelParams } from './GmPolicyPriorModel';

export class GmPolicyPriorOrgan implements Organ<{ stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }, { scores: number[] }> {
  type = OrganType.PolicyPrior;
  version = 'v1';
  domain = 'gm';

  private model?: GmPolicyPriorModel;

  constructor(params?: GmPolicyPriorModelParams) {
    this.model = params ? GmPolicyPriorModel.fromJSON(params) : undefined;
  }

  async predict(input: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }, ctx: OrganContext): Promise<{ scores: number[] }> {
    if (this.model && ctx.computeBudget > 5) {
      ctx.computeBudget -= 5;
      return { scores: this.model.score(input) };
    } else {
      return { scores: this.heuristic(input) };
    }
  }

  private heuristic(input: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }): number[] {
    const { stateFeatures, actionFeaturesList } = input;
    const confusion = (stateFeatures.sparse?.confusion as number) || 0;
    const unresolvedQuestions = (stateFeatures.sparse?.unresolvedQuestions as number) || 0;
    const turnCount = (stateFeatures.dense?.[0] as number) || 0;
    return actionFeaturesList.map(action => {
      let score = 0.5;
      if (confusion > 0.3 && ((action.dense?.[0] as number) || 0) === 1) score += 0.3; // ask_clarification
      if (unresolvedQuestions > 0 && ((action.dense?.[1] as number) || 0) === 1) score += 0.2; // answer_question
      if (turnCount > 5 && ((action.dense?.[2] as number) || 0) === 1) score += 0.2; // summarize
      return Math.max(0, Math.min(1, score));
    });
  }

  static loadFromParams(params: GmPolicyPriorModelParams): GmPolicyPriorOrgan {
    return new GmPolicyPriorOrgan(params);
  }

  exportParams(): GmPolicyPriorModelParams | undefined {
    return this.model?.toJSON();
  }
}
