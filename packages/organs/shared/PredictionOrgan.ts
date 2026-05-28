import { Organ, OrganContext, OrganType } from '../registry';
import { StateFeatures } from '../../core/amplification/features';
import { clamp01, toNumber } from '../../core/utils/normalization';
import { SharedOrganBackbone, SharedOrganFeatures } from './SharedOrganBackbone';

export interface PredictionOrganParams {
  threshold: number;
  incidentWeight: number;
  uncertaintyWeight: number;
  safetyWeight: number;
  latencyWeight: number;
  headWeight: number;
}

export interface PredictionOrganOutput {
  predictionScore: number;
  confidence: number;
  direction: 'up' | 'down' | 'flat';
  signals: string[];
  summary: string;
}

export class PredictionOrgan implements Organ<StateFeatures, PredictionOrganOutput> {
  type = OrganType.Prediction;
  version = 'v1';
  domain = 'default';

  private params: PredictionOrganParams;
  private backbone: SharedOrganBackbone;

  constructor(params?: Partial<PredictionOrganParams>) {
    this.params = {
      threshold: params?.threshold ?? 0.55,
      incidentWeight: params?.incidentWeight ?? 0.35,
      uncertaintyWeight: params?.uncertaintyWeight ?? 0.25,
      safetyWeight: params?.safetyWeight ?? 0.2,
      latencyWeight: params?.latencyWeight ?? 0.15,
      headWeight: params?.headWeight ?? 0.6,
    };
    this.backbone = new SharedOrganBackbone('prediction');
  }

  async predict(input: StateFeatures, ctx: OrganContext): Promise<PredictionOrganOutput> {
    if (ctx.computeBudget > 2) {
      ctx.computeBudget -= 2;
    }

    const features = this.backbone.encodeState(input);
    const score = this.scoreState(input, features);
    const signals = this.collectSignals(input, features);
    const confidence = clamp01(0.25 + Math.abs(score - 0.5) * 1.5 + signals.length * 0.05 + features.latentStrength * 0.05);
    const direction = score > this.params.threshold + 0.08 ? 'up' : score < this.params.threshold - 0.08 ? 'down' : 'flat';
    const summary = this.buildSummary(score, direction, signals, features);

    return { predictionScore: score, confidence, direction, signals, summary };
  }

  train(samples: Array<{ features: StateFeatures; target: number }>): void {
    if (samples.length === 0) return;

    let positiveMean = 0;
    let negativeMean = 0;
    let positiveCount = 0;
    let negativeCount = 0;

    for (const sample of samples) {
      const features = this.backbone.encodeState(sample.features);
      const score = this.scoreState(sample.features, features);
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

  exportParams(): PredictionOrganParams {
    return { ...this.params };
  }

  static loadFromParams(params: PredictionOrganParams): PredictionOrgan {
    return new PredictionOrgan(params);
  }

  private scoreState(input: StateFeatures, features: SharedOrganFeatures): number {
    const criticalIncidents = toNumber(input.sparse?.criticalIncidents);
    const unresolvedIncidents = toNumber(input.sparse?.unresolvedIncidents);
    const unresolvedQuestions = toNumber(input.sparse?.unresolvedQuestions);
    const confusion = toNumber(input.sparse?.confusion);
    const frustration = toNumber(input.sparse?.frustration);
    const safety = toNumber(input.sparse?.safety);
    const avgLatency = toNumber(input.sparse?.avgServiceLatency) / 500;
    const hostError = toNumber(input.sparse?.avgHostErrorRate);
    const combatActive = toNumber(input.sparse?.combatActive);
    const topicCount = toNumber(input.sparse?.topicCount) / 10;

    const rawScore =
      features.latentStrength * this.params.headWeight +
      criticalIncidents * this.params.incidentWeight * 0.5 +
      unresolvedIncidents * this.params.incidentWeight * 0.35 +
      unresolvedQuestions * this.params.uncertaintyWeight * 0.25 +
      confusion * this.params.uncertaintyWeight * 0.45 +
      frustration * this.params.uncertaintyWeight * 0.2 +
      avgLatency * this.params.latencyWeight +
      hostError * this.params.latencyWeight * 0.8 +
      combatActive * 0.2 +
      topicCount * 0.05 -
      safety * this.params.safetyWeight;

    return clamp01(0.5 + rawScore);
  }

  private collectSignals(input: StateFeatures, features: SharedOrganFeatures): string[] {
    const signals: string[] = [...features.signals];
    if (toNumber(input.sparse?.criticalIncidents) > 0) signals.push('critical_incidents');
    if (toNumber(input.sparse?.unresolvedIncidents) > 0) signals.push('unresolved_incidents');
    if (toNumber(input.sparse?.unresolvedQuestions) > 0) signals.push('unresolved_questions');
    if (toNumber(input.sparse?.confusion) > 0.3) signals.push('confusion');
    if (toNumber(input.sparse?.frustration) > 0.3) signals.push('frustration');
    if (toNumber(input.sparse?.avgServiceLatency) > 0) signals.push('latency_pressure');
    if (toNumber(input.sparse?.avgHostErrorRate) > 0) signals.push('host_error_pressure');
    if (toNumber(input.sparse?.combatActive) > 0) signals.push('combat_active');
    return Array.from(new Set(signals));
  }

  private buildSummary(score: number, direction: 'up' | 'down' | 'flat', signals: string[], features: SharedOrganFeatures): string {
    if (signals.length === 0) {
      return `Prediction is ${direction} with score ${score.toFixed(2)} and latent strength ${features.latentStrength.toFixed(2)}.`;
    }
    return `Prediction is ${direction} with score ${score.toFixed(2)} driven by ${signals.join(', ')}.`;
  }
}
