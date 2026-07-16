// domains/chat/featureAdapters.ts
// Chat feature adapters mapping domain data to generic feature views for Synthesus 3.0

import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from '../../amplification/features';
import { ChatWorldState, ChatAction, ChatHistory, ChatFocusTarget } from './types';
import { toNumber } from '../../utils/normalization';

export function chatStateToStateFeatures(state: ChatWorldState): StateFeatures {
  const dense: number[] = [
    state.turnCount / 10, // normalize turn count
    state.unresolvedQuestions,
    state.flags.confusion ? 1 : 0,
    state.flags.safety ? 1 : 0,
    state.flags.frustration ? 1 : 0,
    state.inferredGoals.length / 5, // normalize goals
  ];
  const sparse: Record<string, number | string> = {
    topicCount: state.topics.length,
    lastClarification: Date.now() - (state.history.find(t => t.message.includes('?'))?.timestamp?.getTime() || Date.now()), // time since last ?
    unresolvedQuestions: state.unresolvedQuestions,
    confusion: state.flags.confusion ? 1 : 0,
    safety: state.flags.safety ? 1 : 0,
    frustration: state.flags.frustration ? 1 : 0,
  };
  return { dense, sparse };
}

export function chatActionToActionFeatures(state: ChatWorldState, action: ChatAction): ActionFeatures {
  const dense: number[] = [
    action.type === 'ask_clarification' ? 1 : 0,
    action.type === 'answer_question' ? 1 : 0,
    action.type === 'summarize' ? 1 : 0,
    action.type === 'propose_plan' ? 1 : 0,
    action.type === 'escalate' ? 1 : 0,
  ];
  const sparse: Record<string, number | string> = {
    actionType: action.type,
    contentLength: action.content.length / 100, // normalize
    hasQuestion: action.content.includes('?') ? 1 : 0,
    confusionLevel: state.flags.confusion ? 1 : 0,
  };
  return { dense, sparse };
}

export function chatHistoryToTrajectoryFeatures(history: ChatHistory): TrajectoryFeatures {
  const userTurns = history.turns.filter(t => t.speaker === 'user').length;
  const systemTurns = history.turns.filter(t => t.speaker === 'system').length;
  const confusionTurns = history.turns.filter(t => toNumber(t.metadata?.confusion) > 0.5).length;
  const safetyTurns = history.turns.filter(t => toNumber(t.metadata?.safety) > 0.5).length;
  const dense: number[] = [
    history.turns.length,
    userTurns,
    systemTurns,
    confusionTurns / Math.max(1, history.turns.length),
    safetyTurns / Math.max(1, history.turns.length),
  ];
  const sparse: Record<string, number | string> = {
    confusionRate: confusionTurns / Math.max(1, history.turns.length),
    safetyRate: safetyTurns / Math.max(1, history.turns.length),
    resolution: (systemTurns - confusionTurns) / Math.max(1, systemTurns), // simple proxy
    turnBalance: userTurns / Math.max(1, systemTurns),
  };
  return { dense, sparse };
}

export function chatMultiFocusToMultiFocusFeatures(targets: ChatFocusTarget[]): MultiFocusFeatures {
  const mappedTargets = targets.map(t => ({
    id: t.id,
    dense: [
      t.importance,
      t.urgency,
      (Date.now() - t.lastMentioned.getTime()) / (1000 * 60 * 60 * 24), // days since last mentioned
    ],
    sparse: {
      type: t.type,
      importance: t.importance,
      urgency: t.urgency,
      lastMentioned: t.lastMentioned.getTime(),
    },
  }));
  return { targets: mappedTargets };
}
