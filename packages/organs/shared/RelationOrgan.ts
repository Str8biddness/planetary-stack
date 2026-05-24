import { Organ, OrganContext, OrganType } from '../registry';
import { StateFeatures } from '../../amplification/features';
import { clamp01, toNumber } from '../../utils/normalization';
import { SharedOrganBackbone, SharedOrganFeatures } from './SharedOrganBackbone';

export interface RelationOrganParams {
  threshold: number;
  trustWeight: number;
  rapportWeight: number;
  conflictWeight: number;
  headWeight: number;
}

export interface RelationOrganOutput {
  relationScore: number;
  trust: number;
  rapport: number;
  conflict: number;
  summary: string;
}

export class RelationOrgan implements Organ<StateFeatures, RelationOrganOutput> {
  type = OrganType.Relation;
  version = 'v1';
  domain = 'default';

  private params: RelationOrganParams;
  private backbone: SharedOrganBackbone;

  constructor(params?: Partial<RelationOrganParams>) {
    this.params = {
      threshold: params?.threshold ?? 0.5,
      trustWeight: params?.trustWeight ?? 0.4,
      rapportWeight: params?.rapportWeight ?? 0.35,
      conflictWeight: params?.conflictWeight ?? 0.35,
      headWeight: params?.headWeight ?? 0.5,
    };
    this.backbone = new SharedOrganBackbone('relation');
  }

  async predict(input: StateFeatures, ctx: OrganContext): Promise<RelationOrganOutput> {
    if (ctx.computeBudget > 2) {
      ctx.computeBudget -= 2;
    }

    const features = this.backbone.encodeState(input);
    const trust = this.scoreTrust(input, features);
    const rapport = this.scoreRapport(input, features);
    const conflict = this.scoreConflict(input, features);
    const relationScore = clamp01(0.5 + trust * this.params.trustWeight + rapport * this.params.rapportWeight - conflict * this.params.conflictWeight);
    const summary = `Relation score ${relationScore.toFixed(2)} with trust ${trust.toFixed(2)}, rapport ${rapport.toFixed(2)}, conflict ${conflict.toFixed(2)}.`;

    return { relationScore, trust, rapport, conflict, summary };
  }

  train(samples: Array<{ features: StateFeatures; target: number }>): void {
    if (samples.length === 0) return;

    let positiveMean = 0;
    let negativeMean = 0;
    let positiveCount = 0;
    let negativeCount = 0;

    for (const sample of samples) {
      const features = this.backbone.encodeState(sample.features);
      const score = this.scoreTrust(sample.features, features) + this.scoreRapport(sample.features, features) - this.scoreConflict(sample.features, features);
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

  exportParams(): RelationOrganParams {
    return { ...this.params };
  }

  static loadFromParams(params: RelationOrganParams): RelationOrgan {
    return new RelationOrgan(params);
  }

  private scoreTrust(input: StateFeatures, features: SharedOrganFeatures): number {
    const safety = toNumber(input.sparse?.safety);
    const clarity = toNumber(input.sparse?.clarity);
    const stability = toNumber(input.sparse?.stability);
    return clamp01(features.latentStrength * this.params.headWeight + safety * 0.35 + clarity * 0.35 + stability * 0.3);
  }

  private scoreRapport(input: StateFeatures, features: SharedOrganFeatures): number {
    const topics = toNumber(input.sparse?.topicCount);
    const resolution = toNumber(input.sparse?.resolution);
    const engagement = toNumber(input.sparse?.engagement);
    return clamp01(features.latentStrength * 0.2 + topics * 0.05 + resolution * 0.4 + engagement * 0.25);
  }

  private scoreConflict(input: StateFeatures, features: SharedOrganFeatures): number {
    const frustration = toNumber(input.sparse?.frustration);
    const confusion = toNumber(input.sparse?.confusion);
    const unresolvedQuestions = toNumber(input.sparse?.unresolvedQuestions);
    return clamp01(features.latentStrength * 0.15 + frustration * 0.35 + confusion * 0.35 + unresolvedQuestions * 0.05);
  }
}
