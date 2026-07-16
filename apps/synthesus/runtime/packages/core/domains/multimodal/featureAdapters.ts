// domains/multimodal/featureAdapters.ts
// Multimodal feature adapters mapping domain data to generic feature views

import { StateFeatures, MultiFocusFeatures } from '../../amplification/features';
import {
  MultimodalWorldState,
  MultimodalAction,
  MultimodalTurn,
  MultimodalFocusTarget,
  AlignmentState,
} from './types';

export function multimodalStateToStateFeatures(state: MultimodalWorldState): StateFeatures {
  const dense: number[] = [
    state.vision ? 1 : 0,
    state.voice ? 1 : 0,
    state.text ? 1 : 0,
    state.alignment.confidence,
    state.alignment.visionTextScore ?? 0.5,
    state.alignment.voiceTextScore ?? 0.5,
    state.alignment.visionVoiceScore ?? 0.5,
    state.alignment.modalityWeights.vision,
    state.alignment.modalityWeights.voice,
    state.alignment.modalityWeights.text,
    state.history.length / 20,
    state.vision?.features?.objects.length ?? 0 / 10,
    state.voice?.transcript ? state.voice.transcript.confidence : 0,
    state.voice?.emotion ? state.voice.emotion.confidence : 0,
    state.text?.tokens ? state.text.tokens / 100 : 0,
  ];

  const sparse: Record<string, number | string> = {
    hasVision: state.vision ? 1 : 0,
    hasVoice: state.voice ? 1 : 0,
    hasText: state.text ? 1 : 0,
    visionConfidence: state.vision?.features?.scene.confidence ?? 0,
    voiceConfidence: state.voice?.transcript?.confidence ?? 0,
    textTokens: state.text?.tokens ?? 0,
    alignmentConfidence: state.alignment.confidence,
    alignmentScore: ((state.alignment.visionTextScore ?? 0.5) + (state.alignment.voiceTextScore ?? 0.5) + (state.alignment.visionVoiceScore ?? 0.5)) / 3,
    dominantModality: getDominantModality(state.alignment.modalityWeights),
    turnCount: state.history.length,
  };

  return { dense, sparse };
}

export function multimodalActionToActionFeatures(
  state: MultimodalWorldState,
  action: MultimodalAction
): StateFeatures {
  const dense: number[] = [
    action.type === 'respond_text' ? 1 : 0,
    action.type === 'respond_voice' ? 1 : 0,
    action.type === 'respond_multimodal' ? 1 : 0,
    action.type === 'clarify' ? 1 : 0,
    action.type === 'escalate' ? 1 : 0,
    action.responseConfig?.generateAudio ? 1 : 0,
    action.responseConfig?.highlightVisualRegions?.length ? 1 : 0,
    state.vision ? 1 : 0,
    state.voice ? 1 : 0,
    state.text ? 1 : 0,
  ];

  const sparse: Record<string, number | string> = {
    actionType: action.type,
    hasVisionInput: state.vision ? 1 : 0,
    hasVoiceInput: state.voice ? 1 : 0,
    hasTextInput: state.text ? 1 : 0,
    requiresAudio: action.responseConfig?.generateAudio ? 1 : 0,
    requiresVisualHighlight: action.responseConfig?.highlightVisualRegions?.length ? 1 : 0,
  };

  return { dense, sparse };
}

export function multimodalHistoryToTrajectoryFeatures(history: { turns: MultimodalTurn[] }): StateFeatures {
  const turns = history.turns || [];
  const visionTurns = turns.filter(t => t.modalities.vision).length;
  const voiceTurns = turns.filter(t => t.modalities.voice).length;
  const textTurns = turns.filter(t => t.modalities.text).length;

  const dense: number[] = [
    turns.length,
    visionTurns,
    voiceTurns,
    textTurns,
    turns.length > 0 ? visionTurns / turns.length : 0,
    turns.length > 0 ? voiceTurns / turns.length : 0,
    turns.length > 0 ? textTurns / turns.length : 0,
  ];

  const sparse: Record<string, number | string> = {
    totalTurns: turns.length,
    visionTurns,
    voiceTurns,
    textTurns,
    multimodalTurns: turns.filter(t =>
      (t.modalities.vision ? 1 : 0) +
      (t.modalities.voice ? 1 : 0) +
      (t.modalities.text ? 1 : 0) >= 2
    ).length,
  };

  return { dense, sparse };
}

export function multimodalMultiFocusToMultiFocusFeatures(targets: MultimodalFocusTarget[]): MultiFocusFeatures {
  const mappedTargets = targets.map(t => {
    const dense: number[] = [
      t.importance,
      t.urgency,
      t.recency,
      t.type === 'visual_object' ? 1 : 0,
      t.type === 'speaker' ? 1 : 0,
      t.type === 'text_concept' ? 1 : 0,
      t.type === 'cross_modal_pattern' ? 1 : 0,
    ];

    const sparse: Record<string, number | string> = {
      id: t.id,
      type: t.type,
      importance: t.importance,
      urgency: t.urgency,
      recency: t.recency,
    };

    // Add type-specific sparse features
    if (t.visualRef) {
      sparse.visualObject = t.visualRef.objectLabel;
    }
    if (t.speakerRef) {
      sparse.speakerKnown = t.speakerRef.speakerId ? 1 : 0;
    }
    if (t.textRef) {
      sparse.conceptMentions = t.textRef.mentions;
    }

    return { id: t.id, dense, sparse };
  });

  return { targets: mappedTargets };
}

function getDominantModality(weights: AlignmentState['modalityWeights']): string {
  if (weights.vision >= weights.voice && weights.vision >= weights.text) {
    return 'vision';
  }
  if (weights.voice >= weights.text) {
    return 'voice';
  }
  return 'text';
}
