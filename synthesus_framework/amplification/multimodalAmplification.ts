// amplification/multimodalAmplification.ts
// Multimodal domain amplification implementations for Synthesus 3.0

import { AmplificationContext, IntakeAmplificationResult, PlanningAmplificationResult, OutputAmplificationResult } from './index';
import { MlOrgansHub } from './mlOrgansHub';
import { OrganType } from '../organs/registry';
import {
  multimodalStateToStateFeatures,
  multimodalActionToActionFeatures,
  multimodalHistoryToTrajectoryFeatures,
  multimodalMultiFocusToMultiFocusFeatures,
} from '../domains/multimodal/featureAdapters';
import { MultimodalWorldState, MultimodalAction, MultimodalFocusTarget, MultimodalTurn } from '../domains/multimodal/types';
import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from './features';
import { enforceAutonomy } from '../utils/guardrails';
import { getCrossModalAligner } from '../multimodal/crossModalAlignment';

// Simple RolloutAmplifier stub for Multimodal
class MultimodalRolloutAmplifier {
  static async simulate(
    state: MultimodalWorldState,
    actions: MultimodalAction[],
    horizon: number = 3
  ): Promise<{ trajectory: TrajectoryFeatures; action: MultimodalAction }[]> {
    return actions.map(action => ({
      trajectory: multimodalHistoryToTrajectoryFeatures({
        turns: state.history.slice(-horizon * 2),
      }),
      action,
    }));
  }
}

export async function amplifyIntake(
  ctx: AmplificationContext,
  input: { worldState: MultimodalWorldState; rawInput: any }
): Promise<IntakeAmplificationResult> {
  // Process multimodal inputs through cross-modal aligner
  const aligner = getCrossModalAligner();

  // If we have raw multimodal input, process it
  if (input.rawInput?.query) {
    try {
      const aligned = await aligner.processMultimodalQuery(input.rawInput.query);

      // Update world state with alignment results
      input.worldState.alignment = {
        confidence: aligned.confidence,
        modalityWeights: aligned.modalityWeights,
        visionTextScore: aligned.visionTextAlignment?.crossModalScore,
        voiceTextScore: aligned.voiceTextAlignment?.crossModalScore,
        visionVoiceScore: aligned.visionVoiceAlignment,
        fusedEmbedding: aligned.fusedEmbedding,
      };
    } catch (e) {
      // Graceful fallback - continue with existing world state
    }
  }

  const stateFeatures = multimodalStateToStateFeatures(input.worldState);
  const summary = await MlOrgansHub.summarizeWithSummarizer(stateFeatures, ctx);
  const anomaly = await MlOrgansHub.detectEventsWithAnomalyEvent(stateFeatures, ctx);

  return {
    summaries: [summary],
    anomalyFlags: anomaly ? [anomaly] : [],
  };
}

export async function amplifyPlanning(
  ctx: AmplificationContext,
  input: { worldState: MultimodalWorldState; candidateActions: MultimodalAction[] }
): Promise<PlanningAmplificationResult> {
  const stateFeatures = multimodalStateToStateFeatures(input.worldState);
  const actionFeaturesList = input.candidateActions.map(a =>
    multimodalActionToActionFeatures(input.worldState, a)
  );
  const policyScores = await MlOrgansHub.scoreActionsWithPolicyPrior(
    stateFeatures,
    actionFeaturesList,
    ctx
  );

  // Build focus targets from detected objects, speakers, and concepts
  const focusTargets: MultimodalFocusTarget[] = [];

  // Add visual objects as focus targets
  if (input.worldState.vision?.features?.objects) {
    input.worldState.vision.features.objects.forEach((obj, idx) => {
      focusTargets.push({
        id: `vision-${idx}`,
        type: 'visual_object',
        visualRef: {
          objectLabel: obj.label,
          bbox: obj.bbox,
        },
        importance: obj.confidence,
        urgency: 0.5,
        recency: 1.0,
        lastMentioned: new Date(),
      });
    });
  }

  // Add speaker as focus target
  if (input.worldState.voice?.speaker) {
    focusTargets.push({
      id: 'speaker-0',
      type: 'speaker',
      speakerRef: {
        speakerId: input.worldState.voice.speaker.speakerId,
        voiceprintConfidence: input.worldState.voice.speaker.confidence,
      },
      importance: input.worldState.voice.speaker.confidence,
      urgency: 0.6,
      recency: 1.0,
      lastMentioned: new Date(),
    });
  }

  // Add text concepts as focus targets
  if (input.worldState.text?.content) {
    // Extract key concepts (simple approach - first few words)
    const concepts = input.worldState.text.content
      .split(/\s+/)
      .slice(0, 5)
      .filter((w, i, arr) => arr.indexOf(w) === i);

    concepts.forEach((concept, idx) => {
      focusTargets.push({
        id: `text-${idx}`,
        type: 'text_concept',
        textRef: {
          concept,
          mentions: 1,
        },
        importance: 0.7 - idx * 0.1,
        urgency: 0.5,
        recency: 1.0,
        lastMentioned: new Date(),
      });
    });
  }

  // Score actions based on alignment with focus targets
  const multiFocusFeatures = multimodalMultiFocusToMultiFocusFeatures(focusTargets);
  await MlOrgansHub.allocateAttentionWithAttentionOrgan(multiFocusFeatures, ctx);

  // Filter and rank actions
  const topActions = input.candidateActions
    .map((action, idx) => ({ action, score: policyScores.scores[idx] }))
    .filter(x => x.score > 0.4) // Lower threshold for multimodal
    .sort((a, b) => b.score - a.score)
    .slice(0, 3)
    .map(x => x.action);

  // Simulate rollouts for top actions
  const rollouts = await MultimodalRolloutAmplifier.simulate(input.worldState, topActions);
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
    topTrajectories: rollouts.map((r, idx) => ({
      trajectory: r.trajectory,
      riskScore: riskScores[idx]?.risk ?? 0.5,
    })),
    references: [],
  };
}

export async function amplifyOutput(
  ctx: AmplificationContext,
  input: { chosenAction: MultimodalAction; updatedWorld: MultimodalWorldState }
): Promise<OutputAmplificationResult> {
  const stateFeatures = multimodalStateToStateFeatures(input.updatedWorld);

  // Get trajectory features from recent history
  const recentTurns = input.updatedWorld.history.slice(-4);
  const riskCheck = await MlOrgansHub.estimateRiskWithRiskOutcome(
    multimodalHistoryToTrajectoryFeatures({ turns: recentTurns }),
    ctx
  );

  const summary = await MlOrgansHub.summarizeWithSummarizer(stateFeatures, ctx);

  // Compute confidence margin from modality alignment
  const confidenceMargin = input.updatedWorld.alignment.confidence;

  // Attention sensitivity based on cross-modal alignment scores
  const alignmentScores = [
    input.updatedWorld.alignment.visionTextScore ?? 0.5,
    input.updatedWorld.alignment.voiceTextScore ?? 0.5,
    input.updatedWorld.alignment.visionVoiceScore ?? 0.5,
  ];
  const attentionSensitivity = 1 - Math.max(...alignmentScores);

  const recommendation = enforceAutonomy(ctx.domain, input.chosenAction.type, {
    riskScore: riskCheck.risk,
    confidenceMargin,
    attentionSensitivity,
  });

  return {
    sanityCheckPassed: riskCheck.risk < 0.8 && confidenceMargin > 0.5,
    operatorExplanation: summary.whatIsBroken || 'Multimodal response ready',
    internalSummary: (summary.likelyCauses || []).join('; ') || 'Cross-modal alignment complete',
    executionRecommendation: recommendation,
  };
}
