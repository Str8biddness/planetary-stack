// amplification/mlOrgansHub.ts
// Hub for calling ML organs with budget tracking in Synthesus 3.0

import { OrganRegistry, OrganType } from '../../organs/registry';
import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from './features';
import { OrganContext } from '../../organs/registry';
import { PredictionOrganOutput } from '../../organs/shared/PredictionOrgan';
import { ForecastOrganOutput } from '../../organs/shared/ForecastOrgan';
import { SequencePredictionOutput } from '../../organs/shared/SequencePredictionOrgan';
import { RelationOrganOutput } from '../../organs/shared/RelationOrgan';
import { MemoryOrganOutput } from '../../organs/shared/MemoryOrgan';

export interface AmplificationContext {
  computeBudget: number;
  sessionId: string;
  domain: string;
  allowedOrgans?: string[];
}

export class MlOrgansHub {
  static async scoreActionsWithPolicyPrior(stateFeatures: StateFeatures, actionFeaturesList: ActionFeatures[], ctx: AmplificationContext): Promise<{ scores: number[] }> {
    const organ = OrganRegistry.getOrgan(OrganType.PolicyPrior, ctx.domain);
    if (!organ || ctx.computeBudget < 5) return { scores: actionFeaturesList.map(() => 0.5) };
    ctx.computeBudget -= 5;
    return organ.predict({ stateFeatures, actionFeaturesList }, ctx);
  }

  static async estimateRiskWithRiskOutcome(trajectoryFeatures: TrajectoryFeatures, ctx: AmplificationContext): Promise<any> {
    const organ = OrganRegistry.getOrgan(OrganType.RiskOutcome, ctx.domain);
    if (!organ || ctx.computeBudget < 5) return { risk: 0.5, stability: 0.5, drama: 0.5 };
    ctx.computeBudget -= 5;
    return organ.predict(trajectoryFeatures, ctx);
  }

  static async allocateAttentionWithAttentionOrgan(multiFocusFeatures: MultiFocusFeatures, ctx: AmplificationContext): Promise<{ attentionWeights: number[] }> {
    const organ = OrganRegistry.getOrgan(OrganType.Attention, ctx.domain);
    if (!organ || ctx.computeBudget < 5) {
      const n = multiFocusFeatures.targets.length;
      return { attentionWeights: Array(n).fill(1 / n) };
    }
    ctx.computeBudget -= 5;
    return organ.predict(multiFocusFeatures, ctx);
  }

  static async predictWithPredictionOrgan(stateFeatures: StateFeatures, ctx: AmplificationContext): Promise<PredictionOrganOutput> {
    const organ = OrganRegistry.getOrgan(OrganType.Prediction, ctx.domain);
    if (!organ || ctx.computeBudget < 4) {
      return {
        predictionScore: 0.5,
        confidence: 0.25,
        direction: 'flat',
        signals: [],
        summary: 'Fallback prediction used.',
      };
    }
    ctx.computeBudget -= 4;
    return organ.predict(stateFeatures, ctx);
  }

  static async forecastTrajectory(trajectoryFeatures: TrajectoryFeatures, ctx: AmplificationContext): Promise<ForecastOrganOutput> {
    const organ = OrganRegistry.getOrgan(OrganType.Forecast, ctx.domain);
    if (!organ || ctx.computeBudget < 4) {
      return {
        forecastScore: 0.5,
        trend: 'stable',
        confidence: 0.25,
        horizon: 'short-term',
        signals: [],
        summary: 'Fallback forecast used.',
      };
    }
    ctx.computeBudget -= 4;
    return organ.predict(trajectoryFeatures, ctx);
  }

  static async predictSequence(stateFeatures: StateFeatures, trajectoryFeatures: TrajectoryFeatures, ctx: AmplificationContext): Promise<SequencePredictionOutput> {
    const organ = OrganRegistry.getOrgan(OrganType.SequencePrediction, ctx.domain);
    if (!organ || ctx.computeBudget < 4) {
      return {
        sequenceScore: 0.5,
        expectedContinuity: 0.5,
        expectedChurn: 0.5,
        confidence: 0.25,
        summary: 'Fallback sequence prediction used.',
      };
    }
    ctx.computeBudget -= 4;
    return organ.predict({ stateFeatures, trajectoryFeatures }, ctx);
  }

  static async scoreRelation(stateFeatures: StateFeatures, ctx: AmplificationContext): Promise<RelationOrganOutput> {
    const organ = OrganRegistry.getOrgan(OrganType.Relation, ctx.domain);
    if (!organ || ctx.computeBudget < 4) {
      return {
        relationScore: 0.5,
        trust: 0.5,
        rapport: 0.5,
        conflict: 0.5,
        summary: 'Fallback relation score used.',
      };
    }
    ctx.computeBudget -= 4;
    return organ.predict(stateFeatures, ctx);
  }

  static async summarizeMemory(stateFeatures: StateFeatures, ctx: AmplificationContext): Promise<MemoryOrganOutput> {
    const organ = OrganRegistry.getOrgan(OrganType.Memory, ctx.domain);
    if (!organ || ctx.computeBudget < 4) {
      return {
        memoryScore: 0.5,
        salience: 0.5,
        retentionDays: 7,
        volatility: 0.5,
        summary: 'Fallback memory score used.',
      };
    }
    ctx.computeBudget -= 4;
    return organ.predict(stateFeatures, ctx);
  }

  static async detectEventsWithAnomalyEvent(stateFeatures: StateFeatures, ctx: AmplificationContext): Promise<any> {
    const organ = OrganRegistry.getOrgan(OrganType.AnomalyEvent, ctx.domain);
    if (!organ || ctx.computeBudget < 5) return { anomaly: false, eventType: 'none', confidence: 0 };
    ctx.computeBudget -= 5;
    return organ.predict(stateFeatures, ctx);
  }

  static async summarizeWithSummarizer(stateFeatures: StateFeatures, ctx: AmplificationContext): Promise<any> {
    const organ = OrganRegistry.getOrgan(OrganType.Summarizer, ctx.domain);
    if (!organ || ctx.computeBudget < 5) return { whatIsBroken: 'Unknown', likelyCauses: [], mitigationStatus: 'Unknown' };
    ctx.computeBudget -= 5;
    return organ.predict(stateFeatures, ctx);
  }
}
