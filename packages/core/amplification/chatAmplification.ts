// amplification/chatAmplification.ts
// Chat domain amplification implementations for Synthesus 3.0

import { AmplificationContext, IntakeAmplificationResult, PlanningAmplificationResult, OutputAmplificationResult } from './index';
import { MlOrgansHub } from './mlOrgansHub';
import { OrganType } from '../../organs/registry';
import { chatStateToStateFeatures, chatActionToActionFeatures, chatHistoryToTrajectoryFeatures, chatMultiFocusToMultiFocusFeatures } from '../domains/chat/featureAdapters';
import { ChatWorldState, ChatAction, ChatHistory, ChatFocusTarget } from '../domains/chat/types';
import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from './features';
import { enforceAutonomy } from '../utils/guardrails';

// Simple RolloutAmplifier stub for Chat
class ChatRolloutAmplifier {
  static async simulate(state: ChatWorldState, actions: ChatAction[], horizon: number = 3): Promise<{ trajectory: TrajectoryFeatures; action: ChatAction }[]> {
    return actions.map(action => ({
      trajectory: chatHistoryToTrajectoryFeatures({ turns: state.history.slice(-horizon * 2) }),
      action,
    }));
  }
}

export async function amplifyIntake(ctx: AmplificationContext, input: { worldState: ChatWorldState; rawInput: any }): Promise<IntakeAmplificationResult> {
  const stateFeatures = chatStateToStateFeatures(input.worldState);
  const summary = await MlOrgansHub.summarizeWithSummarizer(stateFeatures, ctx);
  const anomaly = await MlOrgansHub.detectEventsWithAnomalyEvent(stateFeatures, ctx);
  return {
    summaries: [summary],
    anomalyFlags: anomaly ? [anomaly] : [],
  };
}

export async function amplifyPlanning(ctx: AmplificationContext, input: { worldState: ChatWorldState; candidateActions: ChatAction[] }): Promise<PlanningAmplificationResult> {
  const stateFeatures = chatStateToStateFeatures(input.worldState);
  const actionFeaturesList = input.candidateActions.map(a => chatActionToActionFeatures(input.worldState, a));
  const policyScores = await MlOrgansHub.scoreActionsWithPolicyPrior(stateFeatures, actionFeaturesList, ctx);

  const focusTargets: ChatFocusTarget[] = input.candidateActions.map((a, idx) => ({
    id: a.type + '-' + idx,
    type: 'goal',
    importance: policyScores.scores[idx],
    urgency: a.type === 'escalate' ? 1.0 : 0.5,
    lastMentioned: new Date(),
  }));
  const multiFocusFeatures = chatMultiFocusToMultiFocusFeatures(focusTargets);
  const attention = await MlOrgansHub.allocateAttentionWithAttentionOrgan(multiFocusFeatures, ctx);

  const topActions = input.candidateActions
    .map((action, idx) => ({ action, score: policyScores.scores[idx] }))
    .filter(x => x.score >= 0.5)
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map(x => x.action);

  const rollouts = await ChatRolloutAmplifier.simulate(input.worldState, topActions);
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

export async function amplifyOutput(ctx: AmplificationContext, input: { chosenAction: ChatAction; updatedWorld: ChatWorldState }): Promise<OutputAmplificationResult> {
  const stateFeatures = chatStateToStateFeatures(input.updatedWorld);
  const riskCheck = await MlOrgansHub.estimateRiskWithRiskOutcome(chatHistoryToTrajectoryFeatures({ turns: input.updatedWorld.history }), ctx);
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
