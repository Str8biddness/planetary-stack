import { Organ, OrganContext, OrganType } from '../registry';
import { StateFeatures } from '../../amplification/features';
import { clamp01, toNumber } from '../../utils/normalization';

export interface AnomalyEventOrganParams {
  threshold: number;
  incidentWeight: number;
  alertWeight: number;
  confusionWeight: number;
  safetyWeight: number;
}

export interface AnomalyEventPrediction {
  anomaly: boolean;
  eventType: 'none' | 'incident_spike' | 'conversation_risk' | 'system_instability';
  confidence: number;
  signals: string[];
}

export class AnomalyEventOrgan implements Organ<StateFeatures, AnomalyEventPrediction> {
  type = OrganType.AnomalyEvent;
  version = 'v1';
  domain = 'default';

  private params: AnomalyEventOrganParams;

  constructor(params?: AnomalyEventOrganParams) {
    this.params = params || {
      threshold: 0.62,
      incidentWeight: 0.4,
      alertWeight: 0.3,
      confusionWeight: 0.2,
      safetyWeight: 0.1,
    };
  }

  async predict(input: StateFeatures, ctx: OrganContext): Promise<AnomalyEventPrediction> {
    if (ctx.computeBudget > 2) {
      ctx.computeBudget -= 2;
    }

    const signals: string[] = [];
    const incidentPressure = toNumber(input.sparse?.criticalIncidents) * 0.15 + toNumber(input.sparse?.unresolvedIncidents) * 0.1;
    const alertPressure = toNumber(input.sparse?.alertCount) * 0.05 + toNumber(input.sparse?.alerts) * 0.05;
    const confusionPressure = toNumber(input.sparse?.confusion) * this.params.confusionWeight + toNumber(input.sparse?.frustration) * 0.1;
    const safetyPressure = toNumber(input.sparse?.safety) * this.params.safetyWeight;

    if (incidentPressure > 0.2) signals.push('incident_pressure');
    if (alertPressure > 0.2) signals.push('alert_pressure');
    if (confusionPressure > 0.2) signals.push('confusion_pressure');
    if (safetyPressure > 0.05) signals.push('safety_pressure');

    const rawScore =
      incidentPressure * this.params.incidentWeight +
      alertPressure * this.params.alertWeight +
      confusionPressure * this.params.confusionWeight +
      safetyPressure * this.params.safetyWeight;

    const confidence = clamp01(rawScore);
    const anomaly = confidence >= this.params.threshold;
    const eventType = anomaly
      ? incidentPressure >= Math.max(alertPressure, confusionPressure)
        ? 'incident_spike'
        : confusionPressure >= alertPressure
          ? 'conversation_risk'
          : 'system_instability'
      : 'none';

    return {
      anomaly,
      eventType,
      confidence,
      signals,
    };
  }

  train(samples: Array<{ features: StateFeatures; label: boolean }>): void {
    if (samples.length === 0) return;

    let positiveMean = 0;
    let negativeMean = 0;
    let positiveCount = 0;
    let negativeCount = 0;

    for (const sample of samples) {
      const incidentPressure = toNumber(sample.features.sparse?.criticalIncidents) * 0.15 + toNumber(sample.features.sparse?.unresolvedIncidents) * 0.1;
      const alertPressure = toNumber(sample.features.sparse?.alertCount) * 0.05 + toNumber(sample.features.sparse?.alerts) * 0.05;
      const confusionPressure = toNumber(sample.features.sparse?.confusion) * this.params.confusionWeight + toNumber(sample.features.sparse?.frustration) * 0.1;
      const score = incidentPressure + alertPressure + confusionPressure;
      if (sample.label) {
        positiveMean += score;
        positiveCount += 1;
      } else {
        negativeMean += score;
        negativeCount += 1;
      }
    }

    if (positiveCount > 0 && negativeCount > 0) {
      const pos = positiveMean / positiveCount;
      const neg = negativeMean / negativeCount;
      this.params.threshold = clamp01((pos + neg) / 2);
    }
  }

  exportParams(): AnomalyEventOrganParams {
    return { ...this.params };
  }

  static loadFromParams(params: AnomalyEventOrganParams): AnomalyEventOrgan {
    return new AnomalyEventOrgan(params);
  }
}
