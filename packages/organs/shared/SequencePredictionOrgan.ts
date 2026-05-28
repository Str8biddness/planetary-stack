import { Organ, OrganContext, OrganType } from '../registry';
import { StateFeatures, TrajectoryFeatures } from '../../core/amplification/features';
import { clamp01, toNumber } from '../../core/utils/normalization';
import { SharedOrganBackbone, SharedOrganFeatures } from './SharedOrganBackbone';

export interface SequencePredictionOrganParams {
  threshold: number;
  continuityWeight: number;
  churnWeight: number;
  headWeight: number;
}

export interface SequencePredictionOutput {
  sequenceScore: number;
  expectedContinuity: number;
  expectedChurn: number;
  confidence: number;
  summary: string;
}

export class SequencePredictionOrgan implements Organ<{ stateFeatures: StateFeatures; trajectoryFeatures: TrajectoryFeatures }, SequencePredictionOutput> {
  type = OrganType.SequencePrediction;
  version = 'v1';
  domain = 'default';

  private params: SequencePredictionOrganParams;
  private backbone: SharedOrganBackbone;

  constructor(params?: Partial<SequencePredictionOrganParams>) {
    this.params = {
      threshold: params?.threshold ?? 0.5,
      continuityWeight: params?.continuityWeight ?? 0.45,
      churnWeight: params?.churnWeight ?? 0.35,
      headWeight: params?.headWeight ?? 0.55,
    };
    this.backbone = new SharedOrganBackbone('sequence-prediction');
  }

  async predict(input: { stateFeatures: StateFeatures; trajectoryFeatures: TrajectoryFeatures }, ctx: OrganContext): Promise<SequencePredictionOutput> {
    if (ctx.computeBudget > 2) {
      ctx.computeBudget -= 2;
    }

    const continuityFeatures = this.backbone.encodeState(input.stateFeatures);
    const trajectoryFeatures = this.backbone.encodeTrajectory(input.trajectoryFeatures);
    const continuity = this.scoreContinuity(input.stateFeatures, input.trajectoryFeatures, continuityFeatures);
    const churn = this.scoreChurn(input.stateFeatures, input.trajectoryFeatures, trajectoryFeatures);
    const sequenceScore = clamp01(0.5 + continuity * this.params.continuityWeight - churn * this.params.churnWeight);
    const confidence = clamp01(0.25 + Math.abs(sequenceScore - 0.5) * 1.6 + toNumber(input.trajectoryFeatures.sparse?.resolution) * 0.1 + continuityFeatures.latentStrength * 0.05);
    const summary = `Sequence score ${sequenceScore.toFixed(2)} with continuity ${continuity.toFixed(2)} and churn ${churn.toFixed(2)}.`;

    return { sequenceScore, expectedContinuity: continuity, expectedChurn: churn, confidence, summary };
  }

  train(samples: Array<{ features: { stateFeatures: StateFeatures; trajectoryFeatures: TrajectoryFeatures }; target: number }>): void {
    if (samples.length === 0) return;

    let positiveMean = 0;
    let negativeMean = 0;
    let positiveCount = 0;
    let negativeCount = 0;

    for (const sample of samples) {
      const continuityFeatures = this.backbone.encodeState(sample.features.stateFeatures);
      const trajectoryFeatures = this.backbone.encodeTrajectory(sample.features.trajectoryFeatures);
      const score = this.scoreContinuity(sample.features.stateFeatures, sample.features.trajectoryFeatures, continuityFeatures) -
        this.scoreChurn(sample.features.stateFeatures, sample.features.trajectoryFeatures, trajectoryFeatures);
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

  exportParams(): SequencePredictionOrganParams {
    return { ...this.params };
  }

  static loadFromParams(params: SequencePredictionOrganParams): SequencePredictionOrgan {
    return new SequencePredictionOrgan(params);
  }

  private scoreContinuity(stateFeatures: StateFeatures, trajectoryFeatures: TrajectoryFeatures, features: SharedOrganFeatures): number {
    const topicCount = toNumber(stateFeatures.sparse?.topicCount);
    const resolution = toNumber(trajectoryFeatures.sparse?.resolution);
    const stability = toNumber(trajectoryFeatures.sparse?.stability);
    const turnBalance = toNumber(trajectoryFeatures.sparse?.turnBalance);
    return clamp01(features.latentStrength * this.params.headWeight + topicCount * 0.05 + resolution * 0.4 + stability * 0.35 + turnBalance * 0.2);
  }

  private scoreChurn(stateFeatures: StateFeatures, trajectoryFeatures: TrajectoryFeatures, features: SharedOrganFeatures): number {
    const unresolvedQuestions = toNumber(stateFeatures.sparse?.unresolvedQuestions);
    const confusionRate = toNumber(trajectoryFeatures.sparse?.confusionRate);
    const incidentRate = toNumber(trajectoryFeatures.sparse?.incidentRate);
    const actionRate = toNumber(trajectoryFeatures.sparse?.actionRate);
    return clamp01(features.latentStrength * 0.2 + unresolvedQuestions * 0.05 + confusionRate * 0.4 + incidentRate * 0.25 + actionRate * 0.15);
  }
}
