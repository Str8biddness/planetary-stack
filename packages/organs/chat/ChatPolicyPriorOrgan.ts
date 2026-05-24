// organs/chat/ChatPolicyPriorOrgan.ts
// Chat PolicyPrior organ with model support

import { Organ, OrganType, OrganContext } from '../registry';
import { StateFeatures, ActionFeatures } from '../../amplification/features';
import { ChatPolicyPriorModel, ChatPolicyPriorModelParams } from './ChatPolicyPriorModel';

export class ChatPolicyPriorOrgan implements Organ<{ stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }, { scores: number[] }> {
  type = OrganType.PolicyPrior;
  version = 'v1';
  domain = 'chat';

  private model?: ChatPolicyPriorModel;

  constructor(params?: ChatPolicyPriorModelParams) {
    this.model = params ? ChatPolicyPriorModel.fromJSON(params) : undefined;
  }

  async predict(input: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }, ctx: OrganContext): Promise<{ scores: number[] }> {
    if (this.model && ctx.computeBudget > 10) {
      ctx.computeBudget -= 5;
      return { scores: this.model.score(input.stateFeatures, input.actionFeaturesList) };
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

  loadFromParams(params: ChatPolicyPriorModelParams): void {
    this.model = ChatPolicyPriorModel.fromJSON(params);
  }

  exportParams(): ChatPolicyPriorModelParams | undefined {
    return this.model?.toJSON();
  }

  static loadFromParams(params: ChatPolicyPriorModelParams): ChatPolicyPriorOrgan {
    return new ChatPolicyPriorOrgan(params);
  }
}
