import { Organ, OrganContext, OrganType } from '../registry';
import { StateFeatures } from '../../amplification/features';
import { clamp01, toNumber } from '../../utils/normalization';

export interface SummarizerOrganParams {
  severityThreshold: number;
  clarityThreshold: number;
}

export interface SummarizerOutput {
  whatIsBroken: string;
  likelyCauses: string[];
  mitigationStatus: string;
  summary: string;
}

export class SummarizerOrgan implements Organ<StateFeatures, SummarizerOutput> {
  type = OrganType.Summarizer;
  version = 'v1';
  domain = 'default';

  private params: SummarizerOrganParams;

  constructor(params?: SummarizerOrganParams) {
    this.params = params || {
      severityThreshold: 0.6,
      clarityThreshold: 0.5,
    };
  }

  async predict(input: StateFeatures, ctx: OrganContext): Promise<SummarizerOutput> {
    if (ctx.computeBudget > 2) {
      ctx.computeBudget -= 2;
    }

    const criticalIncidents = toNumber(input.sparse?.criticalIncidents);
    const unresolvedIncidents = toNumber(input.sparse?.unresolvedIncidents);
    const confusion = toNumber(input.sparse?.confusion);
    const safety = toNumber(input.sparse?.safety);
    const frustration = toNumber(input.sparse?.frustration);
    const alerts = toNumber(input.sparse?.alerts) || toNumber(input.sparse?.alertCount);

    const severity = clamp01(
      criticalIncidents * 0.2 +
      unresolvedIncidents * 0.12 +
      alerts * 0.05 +
      confusion * 0.2 +
      frustration * 0.1 +
      safety * 0.1
    );

    const likelyCauses: string[] = [];
    if (criticalIncidents > 0) likelyCauses.push('critical incidents are active');
    if (unresolvedIncidents > 0) likelyCauses.push('open incidents remain unresolved');
    if (confusion > this.params.clarityThreshold) likelyCauses.push('confusion is elevated');
    if (frustration > 0.4) likelyCauses.push('frustration is rising');
    if (safety > 0.4) likelyCauses.push('safety signals are present');
    if (alerts > 0) likelyCauses.push('alerts are firing');

    const whatIsBroken = likelyCauses.length > 0
      ? likelyCauses[0]
      : 'no major breakage detected';

    const mitigationStatus = severity >= this.params.severityThreshold
      ? 'escalate and stabilize'
      : severity >= 0.3
        ? 'monitor and correct'
        : 'stable';

    const summary = likelyCauses.length > 0
      ? `Severity ${severity.toFixed(2)} with ${likelyCauses.join('; ')}.`
      : 'System is stable and no obvious failure mode is active.';

    return {
      whatIsBroken,
      likelyCauses,
      mitigationStatus,
      summary,
    };
  }

  train(samples: Array<{ features: StateFeatures; target: SummarizerOutput }>): void {
    if (samples.length === 0) return;

    let severeCount = 0;
    let calmCount = 0;
    let severeMean = 0;
    let calmMean = 0;

    for (const sample of samples) {
      const criticalIncidents = toNumber(sample.features.sparse?.criticalIncidents);
      const unresolvedIncidents = toNumber(sample.features.sparse?.unresolvedIncidents);
      const confusion = toNumber(sample.features.sparse?.confusion);
      const score = criticalIncidents * 0.2 + unresolvedIncidents * 0.12 + confusion * 0.2;
      if (sample.target.mitigationStatus === 'escalate and stabilize') {
        severeMean += score;
        severeCount += 1;
      } else {
        calmMean += score;
        calmCount += 1;
      }
    }

    if (severeCount > 0 && calmCount > 0) {
      this.params.severityThreshold = clamp01((severeMean / severeCount + calmMean / calmCount) / 2);
    }
  }

  exportParams(): SummarizerOrganParams {
    return { ...this.params };
  }

  static loadFromParams(params: SummarizerOrganParams): SummarizerOrgan {
    return new SummarizerOrgan(params);
  }
}
