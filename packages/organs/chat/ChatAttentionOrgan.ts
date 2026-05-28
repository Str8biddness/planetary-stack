// organs/chat/ChatAttentionOrgan.ts
// Chat Attention organ with model support

import { Organ, OrganType, OrganContext } from '../registry';
import { MultiFocusFeatures } from '../../core/amplification/features';
import { ChatAttentionModel, ChatAttentionModelParams } from './ChatAttentionModel';

export class ChatAttentionOrgan implements Organ<MultiFocusFeatures, { attentionWeights: number[] }> {
  type = OrganType.Attention;
  version = 'v1';
  domain = 'chat';

  private model?: ChatAttentionModel;

  constructor(params?: ChatAttentionModelParams) {
    this.model = params ? ChatAttentionModel.fromJSON(params) : undefined;
  }

  async predict(input: MultiFocusFeatures, ctx: OrganContext): Promise<{ attentionWeights: number[] }> {
    const useModel = this.model && ctx.computeBudget > 10;
    if (useModel) ctx.computeBudget -= 5;
    
    const modelWeights = useModel ? this.model!.score(input) : null;
    const heuristicWeights = this.heuristic(input);
    
    if (modelWeights) {
      // Basic hybrid: average model and heuristic weights
      return { 
        attentionWeights: modelWeights.map((mw, idx) => (mw + heuristicWeights[idx]) / 2) 
      };
    } else {
      return { attentionWeights: heuristicWeights };
    }
  }

  private heuristic(input: MultiFocusFeatures): number[] {
    const weights = input.targets.map(t => {
      let score = 0.1;
      const importance = (t.sparse?.importance as number) || 0.5;
      const urgency = (t.sparse?.urgency as number) || 0.5;
      const lastMentionedDays = (t.dense?.[2] as number) || 0;
      if (importance > 0.7) score += 0.3;
      if (urgency > 0.5) score += 0.2;
      if (lastMentionedDays < 1) score += 0.2;
      return score;
    });
    const sum = weights.reduce((s, v) => s + v, 0);
    return sum > 0 ? weights.map(v => v / sum) : weights.map(() => 1 / weights.length);
  }

  static loadFromParams(params: ChatAttentionModelParams): ChatAttentionOrgan {
    return new ChatAttentionOrgan(params);
  }

  exportParams(): ChatAttentionModelParams | undefined {
    return this.model?.toJSON();
  }
}
