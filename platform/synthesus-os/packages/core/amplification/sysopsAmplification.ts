// amplification/sysopsAmplification.ts
// SysOps domain amplification implementations for Synthesus 3.0

import { AmplificationContext, IntakeAmplificationResult, PlanningAmplificationResult, OutputAmplificationResult } from './index';
import { MlOrgansHub } from './mlOrgansHub';
import { OrganType } from '../../organs/registry';
import { sysStateToStateFeatures, sysActionToActionFeatures, sysHistoryToTrajectoryFeatures, sysMultiFocusToMultiFocusFeatures } from '../domains/sysops/featureAdapters';
import { SysWorldState, SysAction, SysHistory, SysFocusTarget } from '../domains/sysops/types';
import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from './features';
import { enforceAutonomy } from '../utils/guardrails';

// Simple RolloutAmplifier stub for SysOps
class SysOpsRolloutAmplifier {
  static async simulate(state: SysWorldState, actions: SysAction[], horizon: number = 3): Promise<{ trajectory: TrajectoryFeatures; action: SysAction }[]> {
    return actions.map(action => ({
      trajectory: sysHistoryToTrajectoryFeatures({ events: [] }), // empty history for stub
      action,
    }));
  }
}

export async function amplifyIntake(ctx: AmplificationContext, input: { worldState: SysWorldState; rawInput: any }): Promise<IntakeAmplificationResult> {
  const stateFeatures = sysStateToStateFeatures(input.worldState);
  const summary = await MlOrgansHub.summarizeWithSummarizer(stateFeatures, ctx);
  const anomaly = await MlOrgansHub.detectEventsWithAnomalyEvent(stateFeatures, ctx);
  return {
    summaries: [summary],
    anomalyFlags: anomaly ? [anomaly] : [],
  };
}

export async function amplifyPlanning(ctx: AmplificationContext, input: { worldState: SysWorldState; candidateActions: SysAction[] }): Promise<PlanningAmplificationResult> {
  const stateFeatures = sysStateToStateFeatures(input.worldState);
  const actionFeaturesList = input.candidateActions.map(a => sysActionToActionFeatures(input.worldState, a));
  const policyScores = await MlOrgansHub.scoreActionsWithPolicyPrior(stateFeatures, actionFeaturesList, ctx);
  const focusTargets: SysFocusTarget[] = input.candidateActions.map(a => ({
    id: a.target,
    type: 'service',
    severity: 0.5,
    recency: 0.5,
    connectivity: 0.5,
  }));
  const multiFocusFeatures = sysMultiFocusToMultiFocusFeatures(focusTargets);
  const attention = await MlOrgansHub.allocateAttentionWithAttentionOrgan(multiFocusFeatures, ctx);
  const topActions = input.candidateActions
    .filter((_, idx) => policyScores.scores[idx] > 0.6)
    .slice(0, 3);
  const rollouts = await SysOpsRolloutAmplifier.simulate(input.worldState, topActions);
  const riskScores = await Promise.all(
    rollouts.map(r => MlOrgansHub.estimateRiskWithRiskOutcome(r.trajectory, ctx))
  );
  const rankedActions = topActions.map((action, idx) => ({
    action,
    score: policyScores.scores[input.candidateActions.indexOf(action)],
    trajectory: rollouts[idx]?.trajectory,
    riskScore: riskScores[idx],
  }));
  return {
    rankedActions,
    topTrajectories: rollouts.map(r => ({ trajectory: r.trajectory, riskScore: 0 })),
    references: [],
  };
}

export async function amplifyOutput(ctx: AmplificationContext, input: { chosenAction: SysAction; updatedWorld: SysWorldState }): Promise<OutputAmplificationResult> {
  const stateFeatures = sysStateToStateFeatures(input.updatedWorld);
  const riskCheck = await MlOrgansHub.estimateRiskWithRiskOutcome(sysHistoryToTrajectoryFeatures({ events: [] }), ctx);
  const shouldBlock = riskCheck.risk > 0.8;
  const summary = await MlOrgansHub.summarizeWithSummarizer(stateFeatures, ctx);
  const confidenceMargin = 0.6;
  const attentionSensitivity = 0.2;
  const recommendation = enforceAutonomy(ctx.domain, input.chosenAction.type, {
    riskScore: riskCheck.risk,
    confidenceMargin,
    attentionSensitivity,
  });
  return {
    sanityCheckPassed: !shouldBlock,
    operatorExplanation: summary.whatIsBroken,
    internalSummary: (summary.likelyCauses || []).join('; '),
    executionRecommendation: recommendation,
  };
}
