// organs/chat/ChatRiskOutcomeOrgan.ts
// Chat RiskOutcome organ with model support

import { Organ, OrganType, OrganContext } from '../registry';
import { TrajectoryFeatures } from '../../core/amplification/features';
import { ChatRiskOutcomeModel, ChatRiskOutcomeModelParams } from './ChatRiskOutcomeModel';

export class ChatRiskOutcomeOrgan implements Organ<TrajectoryFeatures, { risk: number; stability: number; drama: number }> {
  type = OrganType.RiskOutcome;
  version = 'v1';
  domain = 'chat';

  private model?: ChatRiskOutcomeModel;

  constructor(params?: ChatRiskOutcomeModelParams) {
    this.model = params ? ChatRiskOutcomeModel.fromJSON(params) : undefined;
  }

  async predict(input: TrajectoryFeatures, ctx: OrganContext): Promise<{ risk: number; stability: number; drama: number }> {
    const risk = this.model && ctx.computeBudget > 10 ? this.model.score(input) : this.heuristicRisk(input);
    const stability = this.heuristicStability(input);
    const drama = this.heuristicDrama(input);
    return { risk, stability, drama };
  }

  private heuristicRisk(input: TrajectoryFeatures): number {
    const confusionRate = (input.sparse?.confusionRate as number) || 0;
    const safetyRate = (input.sparse?.safetyRate as number) || 0;
    let risk = 0.5;
    if (confusionRate > 0.3) risk += 0.3;
    if (safetyRate > 0.1) risk += 0.4;
    return Math.min(1, risk);
  }

  private heuristicStability(input: TrajectoryFeatures): number {
    const resolution = (input.sparse?.resolution as number) || 0.5;
    return resolution;
  }

  private heuristicDrama(input: TrajectoryFeatures): number {
    const confusionRate = (input.sparse?.confusionRate as number) || 0;
    return confusionRate > 0.5 ? 0.8 : 0.2;
  }

  static loadFromParams(params: ChatRiskOutcomeModelParams): ChatRiskOutcomeOrgan {
    return new ChatRiskOutcomeOrgan(params);
  }

  exportParams(): ChatRiskOutcomeModelParams | undefined {
    return this.model?.toJSON();
  }
}
