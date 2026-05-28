import { Organ, OrganContext, OrganType } from '../registry';
import { StateFeatures } from '../../core/amplification/features';
import { clamp01, toNumber } from '../../core/utils/normalization';
import { SharedOrganBackbone, SharedOrganFeatures } from './SharedOrganBackbone';

export interface MemoryOrganParams {
  threshold: number;
  salienceWeight: number;
  retentionWeight: number;
  volatilityWeight: number;
  headWeight: number;
}

export interface MemoryOrganOutput {
  memoryScore: number;
  salience: number;
  retentionDays: number;
  volatility: number;
  summary: string;
}

export class MemoryOrgan implements Organ<StateFeatures, MemoryOrganOutput> {
  type = OrganType.Memory;
  version = 'v1';
  domain = 'default';

  private params: MemoryOrganParams;
  private backbone: SharedOrganBackbone;

  constructor(params?: Partial<MemoryOrganParams>) {
    this.params = {
      threshold: params?.threshold ?? 0.5,
      salienceWeight: params?.salienceWeight ?? 0.4,
      retentionWeight: params?.retentionWeight ?? 0.35,
      volatilityWeight: params?.volatilityWeight ?? 0.25,
      headWeight: params?.headWeight ?? 0.45,
    };
    this.backbone = new SharedOrganBackbone('memory');
  }

  async predict(input: StateFeatures, ctx: OrganContext): Promise<MemoryOrganOutput> {
    if (ctx.computeBudget > 2) {
      ctx.computeBudget -= 2;
    }

    const features = this.backbone.encodeState(input);
    const salience = this.scoreSalience(input, features);
    const volatility = this.scoreVolatility(input, features);
    const memoryScore = clamp01(0.5 + salience * this.params.salienceWeight - volatility * this.params.volatilityWeight);
    const retentionDays = Math.max(1, Math.round(1 + memoryScore * 13 + salience * 4 - volatility * 3));
    const summary = `Memory score ${memoryScore.toFixed(2)} with salience ${salience.toFixed(2)} and volatility ${volatility.toFixed(2)}.`;

    return { memoryScore, salience, retentionDays, volatility, summary };
  }

  train(samples: Array<{ features: StateFeatures; target: number }>): void {
    if (samples.length === 0) return;

    let positiveMean = 0;
    let negativeMean = 0;
    let positiveCount = 0;
    let negativeCount = 0;

    for (const sample of samples) {
      const features = this.backbone.encodeState(sample.features);
      const score = this.scoreSalience(sample.features, features) - this.scoreVolatility(sample.features, features);
      if (sample.target >= 0.5) {
        positiveMean += score;
        positiveCount += 1;
      } else {
        negativeMean += score;
        negativeCount += 1;
      }
    }

    if (positiveCount > 0 && negativeCount > 0) {
      this.params.threshold = clamp01((positiveMean / positiveCount + negativeMean / negativeCount) / 2);
    }
  }

  exportParams(): MemoryOrganParams {
    return { ...this.params };
  }

  static loadFromParams(params: MemoryOrganParams): MemoryOrgan {
    return new MemoryOrgan(params);
  }

  private scoreSalience(input: StateFeatures, features: SharedOrganFeatures): number {
    const criticalIncidents = toNumber(input.sparse?.criticalIncidents);
    const unresolvedIncidents = toNumber(input.sparse?.unresolvedIncidents);
    const unresolvedQuestions = toNumber(input.sparse?.unresolvedQuestions);
    const confusion = toNumber(input.sparse?.confusion);
    const frustration = toNumber(input.sparse?.frustration);
    const topicCount = toNumber(input.sparse?.topicCount);
    const engagement = toNumber(input.sparse?.engagement);
    return clamp01(
      features.latentStrength * this.params.headWeight +
      criticalIncidents * 0.25 +
      unresolvedIncidents * 0.2 +
      unresolvedQuestions * 0.2 +
      confusion * 0.15 +
      frustration * 0.1 +
      topicCount * 0.03 +
      engagement * 0.07
    );
  }

  private scoreVolatility(input: StateFeatures, features: SharedOrganFeatures): number {
    const safety = toNumber(input.sparse?.safety);
    const clarity = toNumber(input.sparse?.clarity);
    const stability = toNumber(input.sparse?.stability);
    const resolution = toNumber(input.sparse?.resolution);
    const avgLatency = toNumber(input.sparse?.avgServiceLatency) / 500;
    return clamp01(
      features.latentStrength * 0.15 +
      safety * 0.15 +
      clarity * 0.2 +
      stability * 0.35 +
      resolution * 0.2 +
      avgLatency * 0.1
    );
  }
}
