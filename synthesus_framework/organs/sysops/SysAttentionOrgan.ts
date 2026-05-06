// organs/sysops/SysAttentionOrgan.ts
// Heuristic Attention organ for SysOps domain in Synthesus 3.0

import { Organ, OrganType, OrganContext } from '../registry';
import { MultiFocusFeatures } from '../../amplification/features';
import { toNumber } from '../../utils/normalization';

import { SysOpsAttentionModel, SysOpsAttentionModelParams } from './SysOpsAttentionModel';

export class SysAttentionOrgan implements Organ<MultiFocusFeatures, { attentionWeights: number[] }> {
  type = OrganType.Attention;
  version = 'v1';
  domain = 'sysops';

  private model?: SysOpsAttentionModel;

  constructor(params?: SysOpsAttentionModelParams) {
    this.model = params ? SysOpsAttentionModel.fromJSON(params) : undefined;
  }

  async predict(input: MultiFocusFeatures, ctx: OrganContext): Promise<{ attentionWeights: number[] }> {
    const useModel = this.model && ctx.computeBudget > 10;
    if (useModel) ctx.computeBudget -= 5;
    
    const modelWeights = useModel ? this.model!.score(input) : null;
    const heuristicWeights = this.heuristic(input);
    
    if (modelWeights) {
      // Hybrid: average model scores with heuristics
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
      const severity = toNumber(t.sparse?.severity);
      const recency = toNumber(t.sparse?.recency);
      const connectivity = toNumber(t.sparse?.connectivity);
      if (severity > 0.7) score += 0.3;
      if (recency > 0.5) score += 0.2;
      if (connectivity > 0.5) score += 0.2;
      return score;
    });
    const sum = weights.reduce((s, v) => s + v, 0);
    return sum > 0 ? weights.map(v => v / sum) : weights.map(() => 1 / weights.length);
  }

  static loadFromParams(params: SysOpsAttentionModelParams): SysAttentionOrgan {
    return new SysAttentionOrgan(params);
  }

  exportParams(): SysOpsAttentionModelParams | undefined {
    return this.model?.toJSON();
  }
}
