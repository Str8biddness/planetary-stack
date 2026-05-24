import { Organ, OrganContext, OrganType } from '../registry';
import { TrajectoryFeatures } from '../../amplification/features';
import { clamp01, toNumber } from '../../utils/normalization';
import { SharedOrganBackbone, SharedOrganFeatures } from './SharedOrganBackbone';

export interface ForecastOrganParams {
  threshold: number;
  momentumWeight: number;
  stabilityWeight: number;
  volatilityWeight: number;
  horizon: string;
  headWeight: number;
}

export interface ForecastOrganOutput {
  forecastScore: number;
  trend: 'rising' | 'falling' | 'stable';
  confidence: number;
  horizon: string;
  signals: string[];
  summary: string;
}

export class ForecastOrgan implements Organ<TrajectoryFeatures, ForecastOrganOutput> {
  type = OrganType.Forecast;
  version = 'v1';
  domain = 'default';

  private params: ForecastOrganParams;
  private backbone: SharedOrganBackbone;

  constructor(params?: Partial<ForecastOrganParams>) {
    this.params = {
      threshold: params?.threshold ?? 0.52,
      momentumWeight: params?.momentumWeight ?? 0.35,
      stabilityWeight: params?.stabilityWeight ?? 0.3,
      volatilityWeight: params?.volatilityWeight ?? 0.25,
      horizon: params?.horizon ?? 'short-term',
      headWeight: params?.headWeight ?? 0.6,
    };
    this.backbone = new SharedOrganBackbone('forecast');
  }

  async predict(input: TrajectoryFeatures, ctx: OrganContext): Promise<ForecastOrganOutput> {
    if (ctx.computeBudget > 2) {
      ctx.computeBudget -= 2;
    }

    const features = this.backbone.encodeTrajectory(input);
    const score = this.scoreTrajectory(input, features);
    const signals = this.collectSignals(input, features);
    const confidence = clamp01(0.25 + Math.abs(score - 0.5) * 1.5 + signals.length * 0.05 + features.latentStrength * 0.05);
    const trend = score > this.params.threshold + 0.08 ? 'rising' : score < this.params.threshold - 0.08 ? 'falling' : 'stable';
    const summary = this.buildSummary(score, trend, signals, features);

    return { forecastScore: score, trend, confidence, horizon: this.params.horizon, signals, summary };
  }

  train(samples: Array<{ features: TrajectoryFeatures; target: number }>): void {
    if (samples.length === 0) return;

    let positiveMean = 0;
    let negativeMean = 0;
    let positiveCount = 0;
    let negativeCount = 0;

    for (const sample of samples) {
      const features = this.backbone.encodeTrajectory(sample.features);
      const score = this.scoreTrajectory(sample.features, features);
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

  exportParams(): ForecastOrganParams {
    return { ...this.params };
  }

  static loadFromParams(params: ForecastOrganParams): ForecastOrgan {
    return new ForecastOrgan(params);
  }

  private scoreTrajectory(input: TrajectoryFeatures, features: SharedOrganFeatures): number {
    const confusionRate = toNumber(input.sparse?.confusionRate);
    const safetyRate = toNumber(input.sparse?.safetyRate);
    const resolution = toNumber(input.sparse?.resolution);
    const turnBalance = toNumber(input.sparse?.turnBalance);
    const incidentRate = toNumber(input.sparse?.incidentRate);
    const actionRate = toNumber(input.sparse?.actionRate);
    const deployRate = toNumber(input.sparse?.deployRate);
    const stability = toNumber(input.sparse?.stability);
    const spawnRate = toNumber(input.sparse?.spawnRate);
    const combatRate = toNumber(input.sparse?.combatRate);
    const npcTickRate = toNumber(input.sparse?.npcTickRate);

    const rawScore =
      features.latentStrength * this.params.headWeight +
      confusionRate * this.params.volatilityWeight * 0.4 +
      incidentRate * this.params.volatilityWeight * 0.5 +
      combatRate * this.params.volatilityWeight * 0.45 +
      spawnRate * this.params.volatilityWeight * 0.3 +
      npcTickRate * this.params.momentumWeight * 0.15 +
      actionRate * this.params.momentumWeight * 0.2 +
      deployRate * this.params.momentumWeight * 0.15 +
      turnBalance * this.params.momentumWeight * 0.1 +
      resolution * this.params.stabilityWeight * 0.2 +
      stability * this.params.stabilityWeight * 0.45 -
      safetyRate * this.params.stabilityWeight * 0.2;

    return clamp01(0.5 + rawScore);
  }

  private collectSignals(input: TrajectoryFeatures, features: SharedOrganFeatures): string[] {
    const signals: string[] = [...features.signals];
    if (toNumber(input.sparse?.confusionRate) > 0.3) signals.push('confusion_rate');
    if (toNumber(input.sparse?.incidentRate) > 0.2) signals.push('incident_rate');
    if (toNumber(input.sparse?.combatRate) > 0.2) signals.push('combat_rate');
    if (toNumber(input.sparse?.stability) > 0.6) signals.push('stability');
    if (toNumber(input.sparse?.resolution) > 0.5) signals.push('resolution');
    if (toNumber(input.sparse?.deployRate) > 0.2) signals.push('deploy_rate');
    if (toNumber(input.sparse?.actionRate) > 0.2) signals.push('action_rate');
    return Array.from(new Set(signals)).slice(0, 8);
  }

  private buildSummary(score: number, trend: 'rising' | 'falling' | 'stable', signals: string[], features: SharedOrganFeatures): string {
    if (signals.length === 0) {
      return `Forecast is ${trend} with score ${score.toFixed(2)} and latent strength ${features.latentStrength.toFixed(2)}.`;
    }
    return `Forecast is ${trend} with score ${score.toFixed(2)} driven by ${signals.join(', ')}.`;
  }
}
