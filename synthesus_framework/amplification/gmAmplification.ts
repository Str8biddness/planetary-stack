// amplification/gmAmplification.ts
// GM domain amplification implementations for Synthesus 3.0

import { AmplificationContext, IntakeAmplificationResult, PlanningAmplificationResult, OutputAmplificationResult } from './index';
import { MlOrgansHub } from './mlOrgansHub';
import { OrganType } from '../organs/registry';
import { gmStateToStateFeatures, gmActionToActionFeatures, gmHistoryToTrajectoryFeatures, gmMultiFocusToMultiFocusFeatures } from '../domains/gm/featureAdapters';
import { GMWorldState, GMAction, GMHistory, GMFocusTarget } from '../domains/gm/types';
import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from './features';
import { enforceAutonomy } from '../utils/guardrails';

// Simple RolloutAmplifier stub for GM
class GmRolloutAmplifier {
  static async simulate(state: GMWorldState, actions: GMAction[], horizon: number = 3): Promise<{ trajectory: TrajectoryFeatures; action: GMAction }[]> {
    return actions.map(action => ({
      trajectory: gmHistoryToTrajectoryFeatures({ events: state.events.slice(-horizon) }),
      action,
    }));
  }
}

export async function amplifyIntake(ctx: AmplificationContext, input: { worldState: GMWorldState; rawInput: any }): Promise<IntakeAmplificationResult> {
  const stateFeatures = gmStateToStateFeatures(input.worldState);
  const summary = await MlOrgansHub.summarizeWithSummarizer(stateFeatures, ctx);
  const anomaly = await MlOrgansHub.detectEventsWithAnomalyEvent(stateFeatures, ctx);
  return {
    summaries: [summary],
    anomalyFlags: anomaly ? [anomaly] : [],
  };
}

export async function amplifyPlanning(ctx: AmplificationContext, input: { worldState: GMWorldState; candidateActions: GMAction[] }): Promise<PlanningAmplificationResult> {
  const stateFeatures = gmStateToStateFeatures(input.worldState);
  const actionFeaturesList = input.candidateActions.map(a => gmActionToActionFeatures(input.worldState, a));
  const policyScores = await MlOrgansHub.scoreActionsWithPolicyPrior(stateFeatures, actionFeaturesList, ctx);

  const focusTargets: GMFocusTarget[] = input.candidateActions.map((a, idx) => ({
    id: a.type + '-' + idx,
    type: 'npc',
    severity: policyScores.scores[idx],
    recency: 0.5,
    connectivity: 0.5,
  }));
  const multiFocusFeatures = gmMultiFocusToMultiFocusFeatures(focusTargets);
  await MlOrgansHub.allocateAttentionWithAttentionOrgan(multiFocusFeatures, ctx);

  const topActions = input.candidateActions
    .map((action, idx) => ({ action, score: policyScores.scores[idx] }))
    .filter(x => x.score > 0.5)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map(x => x.action);

  const rollouts = await GmRolloutAmplifier.simulate(input.worldState, topActions);
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
    topTrajectories: rollouts.map((r, idx) => ({ trajectory: r.trajectory, riskScore: riskScores[idx]?.risk ?? 0.5 })),
    references: [],
  };
}

export async function amplifyOutput(ctx: AmplificationContext, input: { chosenAction: GMAction; updatedWorld: GMWorldState }): Promise<OutputAmplificationResult> {
  const stateFeatures = gmStateToStateFeatures(input.updatedWorld);
  const riskCheck = await MlOrgansHub.estimateRiskWithRiskOutcome(gmHistoryToTrajectoryFeatures({ events: input.updatedWorld.events }), ctx);
  const summary = await MlOrgansHub.summarizeWithSummarizer(stateFeatures, ctx);
  const confidenceMargin = 0.6; // placeholder; compute from PolicyPrior top-two delta in real use
  const attentionSensitivity = 0.2;
  const recommendation = enforceAutonomy(ctx.domain, input.chosenAction.type, {
    riskScore: riskCheck.risk,
    confidenceMargin,
    attentionSensitivity,
  });
  return {
    sanityCheckPassed: riskCheck.risk < 0.8,
    operatorExplanation: summary.whatIsBroken || 'Proceed with recommendation',
    internalSummary: (summary.likelyCauses || []).join('; ') || 'Autonomy check completed',
    executionRecommendation: recommendation,
  };
}
