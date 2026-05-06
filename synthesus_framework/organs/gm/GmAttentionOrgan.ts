// organs/gm/GmAttentionOrgan.ts
// GM Attention organ with model support

import { Organ, OrganType, OrganContext } from '../registry';
import { MultiFocusFeatures } from '../../amplification/features';
import { GmAttentionModel, GmAttentionModelParams } from './GmAttentionModel';

export class GmAttentionOrgan implements Organ<MultiFocusFeatures, { attentionWeights: number[] }> {
  type = OrganType.Attention;
  version = 'v1';
  domain = 'gm';

  private model?: GmAttentionModel;

  constructor(params?: GmAttentionModelParams) {
    this.model = params ? GmAttentionModel.fromJSON(params) : undefined;
  }

  async predict(input: MultiFocusFeatures, ctx: OrganContext): Promise<{ attentionWeights: number[] }> {
    if (this.model && ctx.computeBudget > 5) {
      ctx.computeBudget -= 5;
      return { attentionWeights: this.model.score(input) };
    } else {
      return { attentionWeights: this.heuristic(input) };
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

  static loadFromParams(params: GmAttentionModelParams): GmAttentionOrgan {
    return new GmAttentionOrgan(params);
  }

  exportParams(): GmAttentionModelParams | undefined {
    return this.model?.toJSON();
  }
}
