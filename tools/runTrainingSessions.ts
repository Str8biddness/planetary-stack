// scripts/runTrainingSessions.ts
// Script to run amplified sessions in GM, SysOps, Chat domains and emit diverse training traces

import { SynthesusCoreStub, CoreInput } from '../packages/core/synthetic_core/index';
import { SynthesusCoreSysOps } from '../packages/core/synthetic_core/synthesusCoreSysOps';
import { SynthesusCoreChat } from '../packages/core/synthetic_core/synthesusCoreChat';
import { appendTraceEntry } from '../packages/core/learning/teacherTrace';
import { chatStateToStateFeatures, chatActionToActionFeatures, chatHistoryToTrajectoryFeatures, chatMultiFocusToMultiFocusFeatures } from '../packages/core/domains/chat/featureAdapters';
import { sysStateToStateFeatures, sysActionToActionFeatures, sysHistoryToTrajectoryFeatures, sysMultiFocusToMultiFocusFeatures } from '../packages/core/domains/sysops/featureAdapters';
import { gmStateToStateFeatures, gmActionToActionFeatures, gmHistoryToTrajectoryFeatures, gmMultiFocusToMultiFocusFeatures } from '../packages/core/domains/gm/featureAdapters';
import { ChatWorldState, ChatAction, ChatFocusTarget } from '../packages/core/domains/chat/types';
import { SysWorldState, SysAction, SysFocusTarget, SysHistory } from '../packages/core/domains/sysops/types';
import { GMWorldState, GMAction, GMFocusTarget, GMNpc, GMWorldEvent } from '../packages/core/domains/gm/types';

const GENERATOR_VERSION = 'organ-triad-replay-v2';
const DEFAULT_TRACE_SEED = 950907;
const BASE_TIME_MS = Date.UTC(2026, 4, 30, 12, 0, 0);
const HOUR_MS = 3_600_000;
const DAY_MS = 86_400_000;

class SeededRng {
  private state: number;

  constructor(seed: number) {
    this.state = seed >>> 0;
  }

  next(): number {
    this.state = (1664525 * this.state + 1013904223) >>> 0;
    return this.state / 0x100000000;
  }
}

interface TraceRuntime {
  rng: SeededRng;
  seed: number;
  step: number;
}

function readTraceSeed(): number {
  const parsed = Number.parseInt(process.env.SYNTHESUS_ORGAN_TRACE_SEED ?? '', 10);
  return Number.isFinite(parsed) ? parsed : DEFAULT_TRACE_SEED;
}

function random(runtime: TraceRuntime): number {
  return runtime.rng.next();
}

function timestamp(sessionIndex: number, offsetMs = 0): Date {
  return new Date(BASE_TIME_MS + sessionIndex * 10 * 60_000 + offsetMs);
}

function replay(runtime: TraceRuntime, scenarioId: string, sessionIndex: number, domain: string, organ: string, phase: string) {
  runtime.step += 1;
  const frameStem = `${runtime.seed}-${runtime.step}-${scenarioId}`.replace(/[^a-zA-Z0-9_-]/g, '-');
  return {
    generator: GENERATOR_VERSION,
    seed: runtime.seed,
    scenarioId,
    step: runtime.step,
    simulatedTime: timestamp(sessionIndex).toISOString(),
    chal: {
      frameId: `chal-organ-${frameStem}`,
      parentFrameId: `chal-training-session-${domain}-${sessionIndex}`,
      device: `chal://organs/${domain}/${organ}`,
      role: 'organ_accelerator' as const,
      route: 'organ_training_replay',
      outputRef: `${domain}.${organ}.${phase}`,
    },
  };
}

function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}

function normalizeWeights(values: number[]): number[] {
  if (values.length === 0) return [];
  const sanitized = values.map(value => Math.max(0, value));
  const total = sanitized.reduce((sum, value) => sum + value, 0);
  if (total <= 0) return values.map(() => 1 / values.length);
  return sanitized.map(value => value / total);
}

function jitter(runtime: TraceRuntime, value: number, magnitude = 0.18): number {
  return clamp01(value + (random(runtime) - 0.5) * magnitude);
}

function chooseWeightedIndex(runtime: TraceRuntime, weights: number[], suboptimalChance = 0.2): number {
  if (weights.length === 0) return 0;
  const ranked = weights
    .map((score, idx) => ({ score, idx }))
    .sort((a, b) => b.score - a.score);

  if (weights.length > 1 && random(runtime) < suboptimalChance) {
    const alternatives = ranked.slice(1);
    return alternatives[Math.floor(random(runtime) * alternatives.length)]?.idx ?? ranked[0].idx;
  }

  const total = weights.reduce((sum, value) => sum + Math.max(0, value), 0);
  if (total <= 0) return ranked[0].idx;

  let cursor = random(runtime) * total;
  for (const { score, idx } of ranked) {
    cursor -= Math.max(0, score);
    if (cursor <= 0) return idx;
  }
  return ranked[0].idx;
}

function buildChatWorldState(runtime: TraceRuntime, sessionIndex: number): ChatWorldState {
  const mood = sessionIndex % 4;
  const flags = {
    confusion: mood === 0 || random(runtime) < 0.25,
    safety: mood === 3 || random(runtime) < 0.15,
    frustration: mood === 1 || random(runtime) < 0.2,
  };
  const history = [
    {
      speaker: 'user' as const,
      message: mood === 0 ? 'I am not sure what to do.' : 'Can you help me with this?',
      timestamp: timestamp(sessionIndex, -HOUR_MS),
    },
    {
      speaker: 'system' as const,
      message: mood === 2 ? 'Here is a summary so far.' : 'What is the core constraint?',
      timestamp: timestamp(sessionIndex, -HOUR_MS / 2),
      metadata: { confusion: flags.confusion ? 0.8 : 0.2, safety: flags.safety ? 0.2 : 0.05 },
    },
  ];

  return {
    domain: 'chat',
    conversationId: `chat-session-${sessionIndex}`,
    history,
    inferredGoals: flags.confusion ? ['clarify question', 'reduce ambiguity'] : ['answer question'],
    topics: mood === 2 ? ['planning', 'summary'] : ['help', 'constraints'],
    flags,
    unresolvedQuestions: mood === 0 ? 3 : mood === 1 ? 2 : 1,
    turnCount: 2 + sessionIndex,
    timestamp: timestamp(sessionIndex),
  };
}

function buildChatActions(sessionIndex: number): ChatAction[] {
  const base: ChatAction[] = [
    { type: 'ask_clarification', content: 'Can you clarify the request?', description: 'Ask for more info' },
    { type: 'answer_question', content: 'The answer is...', description: 'Provide answer' },
    { type: 'summarize', content: 'Summary: ...', description: 'Summarize conversation' },
  ];
  const rotation = sessionIndex % base.length;
  return [...base.slice(rotation), ...base.slice(0, rotation)];
}

function scoreChatActions(runtime: TraceRuntime, worldState: ChatWorldState, actions: ChatAction[]): number[] {
  return normalizeWeights(actions.map(action => {
    if (action.type === 'ask_clarification') {
      return worldState.flags.confusion ? 0.95 : 0.35;
    }
    if (action.type === 'answer_question') {
      return worldState.unresolvedQuestions > 0 ? 0.9 : 0.45;
    }
    if (action.type === 'summarize') {
      return worldState.turnCount > 3 ? 0.8 : 0.35;
    }
    return 0.25;
  }).map(score => jitter(runtime, score, 0.24)));
}

function logChatTrace(runtime: TraceRuntime, sessionId: string, worldState: ChatWorldState, actions: ChatAction[], chosenIndex: number, sessionIndex: number): void {
  const stateFeatures = chatStateToStateFeatures(worldState);
  const actionFeatures = actions.map(action => chatActionToActionFeatures(worldState, action));
  const focusTargets: ChatFocusTarget[] = actions.map((action, idx) => ({
    id: `${action.type}-${idx}`,
    type: 'goal',
    importance: clamp01(0.35 + (idx === chosenIndex ? 0.4 : 0.1) + random(runtime) * 0.15),
    urgency: action.type === 'ask_clarification' ? 1 : action.type === 'answer_question' ? 0.8 : 0.45,
    lastMentioned: timestamp(sessionIndex, -Math.floor(random(runtime) * 3) * DAY_MS),
  }));
  const multiFocusFeatures = chatMultiFocusToMultiFocusFeatures(focusTargets);
  const chosenAction = actions[chosenIndex] ?? actions[0];
  const trajectoryFeatures = chatHistoryToTrajectoryFeatures({ turns: worldState.history });
  const policyScores = scoreChatActions(runtime, worldState, actions);
  const attentionWeights = normalizeWeights(focusTargets.map(target => target.importance));
  const quality = clamp01(
    (chosenAction?.type === 'answer_question' ? 0.92 : chosenAction?.type === 'summarize' ? 0.82 : 0.7) +
    (worldState.flags.confusion && chosenAction?.type === 'ask_clarification' ? 0.08 : 0) -
    (chosenIndex === 0 ? 0.03 : 0)
  );

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'planning',
    domain: 'chat',
    organ: 'policy_prior',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { policyScores, attentionWeights },
    decision: chosenAction,
    outcome: { quality },
    trajectoryFeatures,
    replay: replay(runtime, `chat-${sessionIndex}-policy-prior`, sessionIndex, 'chat', 'policy_prior', 'planning'),
  });

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'planning',
    domain: 'chat',
    organ: 'attention',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { attentionWeights },
    decision: chosenAction,
    outcome: { quality },
    trajectoryFeatures,
    replay: replay(runtime, `chat-${sessionIndex}-attention`, sessionIndex, 'chat', 'attention', 'planning'),
  });

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'output',
    domain: 'chat',
    organ: 'risk_outcome',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { attentionWeights },
    decision: chosenAction,
    outcome: {
      quality,
      clarity: clamp01(0.55 + (chosenAction?.type === 'answer_question' ? 0.3 : 0.1) - (worldState.flags.confusion ? 0.05 : 0)),
      resolution: clamp01(0.45 + (chosenAction?.type === 'summarize' ? 0.35 : 0.1)),
      safety: clamp01(worldState.flags.safety ? 1 : 0.88),
      metrics: {
        clarity: clamp01(0.55 + (chosenAction?.type === 'answer_question' ? 0.3 : 0.1) - (worldState.flags.confusion ? 0.05 : 0)),
        resolution: clamp01(0.45 + (chosenAction?.type === 'summarize' ? 0.35 : 0.1)),
        safety: clamp01(worldState.flags.safety ? 1 : 0.88),
      },
    },
    trajectoryFeatures,
    replay: replay(runtime, `chat-${sessionIndex}-risk-outcome`, sessionIndex, 'chat', 'risk_outcome', 'output'),
  });
}

function buildSysOpsWorldState(runtime: TraceRuntime, sessionIndex: number): SysWorldState {
  const hostCount = 2 + (sessionIndex % 3);
  const serviceCount = 2 + (sessionIndex % 2);
  const hosts = Array.from({ length: hostCount }, (_, idx) => ({
    id: `host-${sessionIndex}-${idx}`,
    health: clamp01(0.55 + random(runtime) * 0.4 - (idx === 0 && sessionIndex % 2 === 0 ? 0.25 : 0)),
    errorRate: clamp01(random(runtime) * 0.35 + (idx === 0 ? 0.08 : 0.02)),
    latency: 80 + random(runtime) * 120,
    saturation: clamp01(0.3 + random(runtime) * 0.6),
    lastRestart: random(runtime) < 0.3 ? timestamp(sessionIndex, -DAY_MS) : undefined,
  }));
  const services = Array.from({ length: serviceCount }, (_, idx) => ({
    name: `service-${sessionIndex}-${idx}`,
    health: clamp01(0.6 + random(runtime) * 0.35 - (idx === 1 && sessionIndex % 3 === 0 ? 0.2 : 0)),
    dependencies: idx === 0 ? ['auth'] : ['api', 'db'],
    errorRate: clamp01(random(runtime) * 0.25),
    latency: 100 + random(runtime) * 220,
    lastDeploy: random(runtime) < 0.4 ? timestamp(sessionIndex, -2 * DAY_MS) : undefined,
  }));
  const incidents = [] as SysWorldState['incidents'];
  if (sessionIndex % 2 === 0) {
    incidents.push({
      id: `incident-${sessionIndex}-0`,
      severity: sessionIndex % 4 === 0 ? 'critical' : 'high',
      startTime: timestamp(sessionIndex, -2 * HOUR_MS),
      duration: 7200,
      services: [services[0].name],
      blastRadius: clamp01(0.4 + random(runtime) * 0.4),
      status: sessionIndex % 4 === 0 ? 'open' : 'mitigating',
    });
  }
  if (sessionIndex % 3 === 1) {
    incidents.push({
      id: `incident-${sessionIndex}-1`,
      severity: 'medium',
      startTime: timestamp(sessionIndex, -5 * HOUR_MS),
      duration: 1800,
      services: [services[1]?.name ?? services[0].name],
      blastRadius: clamp01(0.2 + random(runtime) * 0.3),
      status: 'resolved',
    });
  }
  return {
    domain: 'sysops',
    hosts,
    services,
    incidents,
    alerts: sessionIndex % 2 === 0 ? ['latency spike', 'error burst'] : ['routine drift'],
    timestamp: timestamp(sessionIndex),
  };
}

function buildSysOpsActions(sessionIndex: number): SysAction[] {
  const actions: SysAction[] = [
    { type: 'runbook', target: 'service-0', description: 'Run recovery playbook' },
    { type: 'scale', target: 'service-1', description: 'Scale up service' },
    { type: 'restart', target: 'host-0', description: 'Restart host' },
  ];
  if (sessionIndex % 3 === 1) {
    actions.push({ type: 'failover', target: 'service-0', description: 'Fail over to standby' });
  }
  if (sessionIndex % 4 === 0) {
    actions.push({ type: 'rollback', target: 'service-1', description: 'Rollback recent deploy' });
  }
  return actions;
}

function scoreSysOpsActions(runtime: TraceRuntime, worldState: SysWorldState, actions: SysAction[]): number[] {
  const avgHostHealth = worldState.hosts.reduce((sum, host) => sum + host.health, 0) / Math.max(1, worldState.hosts.length);
  const criticalIncident = worldState.incidents.some(incident => incident.severity === 'critical');
  const degradedService = worldState.services.some(service => service.health < 0.65);
  return normalizeWeights(actions.map(action => {
    if (action.type === 'runbook') return criticalIncident ? 0.95 : 0.7;
    if (action.type === 'scale') return degradedService ? 0.88 : 0.55;
    if (action.type === 'restart') return avgHostHealth < 0.7 ? 0.8 : 0.4;
    if (action.type === 'failover') return criticalIncident ? 0.9 : 0.35;
    if (action.type === 'rollback') return degradedService ? 0.76 : 0.3;
    return 0.2;
  }).map(score => jitter(runtime, score, 0.26)));
}

function logSysOpsTrace(runtime: TraceRuntime, sessionId: string, worldState: SysWorldState, actions: SysAction[], chosenIndex: number, sessionIndex: number): void {
  const stateFeatures = sysStateToStateFeatures(worldState);
  const actionFeatures = actions.map(action => sysActionToActionFeatures(worldState, action));
  const focusTargets: SysFocusTarget[] = actions.map((action, idx) => ({
    id: `${action.target}-${idx}`,
    type: 'service',
    severity: clamp01(0.4 + (idx === chosenIndex ? 0.45 : 0.12) + random(runtime) * 0.1),
    recency: clamp01(0.4 + random(runtime) * 0.3),
    connectivity: clamp01(0.35 + random(runtime) * 0.3),
  }));
  const multiFocusFeatures = sysMultiFocusToMultiFocusFeatures(focusTargets);
  const chosenAction = actions[chosenIndex] ?? actions[0];
  const incidentEvents: SysHistory['events'] = worldState.incidents.map(incident => ({
    timestamp: incident.startTime,
    type: 'incident',
    details: { severity: incident.severity, status: incident.status, services: incident.services },
  }));
  const actionEvents: SysHistory['events'] = worldState.hosts.slice(0, 1).map(host => ({
    timestamp: timestamp(sessionIndex),
    type: 'action',
    details: { type: 'restart', target: host.id },
  }));
  const sysEvents: SysHistory['events'] = [...incidentEvents, ...actionEvents];
  const trajectoryFeatures = sysHistoryToTrajectoryFeatures({ events: sysEvents });
  const policyScores = scoreSysOpsActions(runtime, worldState, actions);
  const attentionWeights = normalizeWeights(focusTargets.map(target => target.severity ?? 0.25));
  const quality = clamp01(
    (chosenAction?.type === 'runbook' ? 0.9 : chosenAction?.type === 'failover' ? 0.84 : 0.72) +
    (worldState.incidents.some(incident => incident.severity === 'critical') && chosenAction?.type === 'runbook' ? 0.05 : 0) -
    (chosenIndex === 0 ? 0.02 : 0)
  );

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'planning',
    domain: 'sysops',
    organ: 'policy_prior',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { policyScores, attentionWeights },
    decision: chosenAction,
    outcome: { quality },
    trajectoryFeatures,
    replay: replay(runtime, `sysops-${sessionIndex}-policy-prior`, sessionIndex, 'sysops', 'policy_prior', 'planning'),
  });

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'planning',
    domain: 'sysops',
    organ: 'attention',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { attentionWeights },
    decision: chosenAction,
    outcome: { quality },
    trajectoryFeatures,
    replay: replay(runtime, `sysops-${sessionIndex}-attention`, sessionIndex, 'sysops', 'attention', 'planning'),
  });

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'output',
    domain: 'sysops',
    organ: 'risk_outcome',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { attentionWeights },
    decision: chosenAction,
    outcome: {
      quality,
      stability: clamp01(0.55 + (worldState.hosts.reduce((sum, host) => sum + host.health, 0) / Math.max(1, worldState.hosts.length)) * 0.35),
      sloImpact: clamp01(chosenAction?.type === 'restart' ? 0.35 : chosenAction?.type === 'scale' ? 0.55 : 0.7),
      safety: clamp01(chosenAction?.type === 'runbook' ? 0.95 : 0.9),
      metrics: {
        stability: clamp01(0.55 + (worldState.hosts.reduce((sum, host) => sum + host.health, 0) / Math.max(1, worldState.hosts.length)) * 0.35),
        sloImpact: clamp01(chosenAction?.type === 'restart' ? 0.35 : chosenAction?.type === 'scale' ? 0.55 : 0.7),
        safety: clamp01(chosenAction?.type === 'runbook' ? 0.95 : 0.9),
      },
    },
    trajectoryFeatures,
    replay: replay(runtime, `sysops-${sessionIndex}-risk-outcome`, sessionIndex, 'sysops', 'risk_outcome', 'output'),
  });
}

function buildGMWorldState(runtime: TraceRuntime, sessionIndex: number): GMWorldState {
  const combatActive = sessionIndex % 2 === 0;
  const npcs: GMNpc[] = Array.from({ length: 2 + (sessionIndex % 3) }, (_, idx) => ({
    id: `npc-${sessionIndex}-${idx}`,
    name: `NPC ${sessionIndex}-${idx}`,
    health: clamp01(0.55 + random(runtime) * 0.4 - (combatActive && idx === 0 ? 0.15 : 0)),
    disposition: idx === 0 && combatActive ? 'hostile' : idx === 1 ? 'friendly' : 'neutral',
    location: idx === 0 ? 'town-square' : 'market',
    state: combatActive && idx === 0 ? 'combat' : 'idle',
    tags: combatActive ? ['combat', 'urgent'] : ['dialogue', 'lore'],
  }));
  const events: GMWorldEvent[] = [
    {
      timestamp: timestamp(sessionIndex, -HOUR_MS),
      type: 'player_action' as const,
      details: { action: combatActive ? 'attacked' : 'talked' },
    },
    {
      timestamp: timestamp(sessionIndex, -HOUR_MS / 2),
      type: combatActive ? 'combat_start' as const : 'env_change' as const,
      details: { intensity: combatActive ? 'high' : 'medium' },
    },
  ];
  if (sessionIndex % 3 === 0) {
    events.push({
      timestamp: timestamp(sessionIndex, -HOUR_MS / 4),
      type: 'npc_tick',
      details: { mood: 'uneasy' },
    });
  }
  return {
    domain: 'gm',
    tick: 100 + sessionIndex,
    location: combatActive ? 'dungeon' : 'village',
    npcs,
    combat: {
      active: combatActive,
      participants: combatActive ? [npcs[0].id] : [],
      round: combatActive ? 2 + (sessionIndex % 2) : 0,
      playerHealth: clamp01(0.6 + random(runtime) * 0.4 - (combatActive ? 0.2 : 0)),
      enemiesVisible: combatActive ? 2 + (sessionIndex % 2) : 0,
      lastAction: combatActive ? 'attack' : 'dialogue',
    },
    events,
    flags: {
      combatActive,
      playerLowHealth: combatActive && sessionIndex % 3 === 0,
      escalation: sessionIndex % 4 === 0,
    },
    timestamp: timestamp(sessionIndex),
  };
}

function buildGMActions(sessionIndex: number): GMAction[] {
  const actions: GMAction[] = [
    { type: 'dialogue', description: 'Talk to NPCs', target: 'npc-0' },
    { type: 'combat_action', description: 'Resolve combat', target: 'enemy-0' },
    { type: 'escalate', description: 'Escalate to operator', target: 'gm' },
  ];
  if (sessionIndex % 3 === 0) {
    return [actions[1], actions[0], actions[2]];
  }
  if (sessionIndex % 3 === 1) {
    return [actions[0], actions[2], actions[1]];
  }
  return actions;
}

function scoreGMActions(runtime: TraceRuntime, worldState: GMWorldState, actions: GMAction[]): number[] {
  return normalizeWeights(actions.map(action => {
    if (action.type === 'dialogue') return worldState.combat.active ? 0.45 : 0.9;
    if (action.type === 'combat_action') return worldState.combat.active ? 0.92 : 0.4;
    if (action.type === 'escalate') return worldState.flags.escalation ? 0.88 : 0.35;
    return 0.2;
  }).map(score => jitter(runtime, score, 0.25)));
}

function logGmTrace(runtime: TraceRuntime, sessionId: string, worldState: GMWorldState, actions: GMAction[], chosenIndex: number, sessionIndex: number): void {
  const stateFeatures = gmStateToStateFeatures(worldState);
  const actionFeatures = actions.map(action => gmActionToActionFeatures(worldState, action));
  const focusTargets: GMFocusTarget[] = actions.map((action, idx) => ({
    id: `${action.type}-${idx}`,
    type: 'npc',
    severity: clamp01(0.35 + (idx === chosenIndex ? 0.45 : 0.1) + random(runtime) * 0.15),
    recency: clamp01(0.3 + random(runtime) * 0.4),
    connectivity: clamp01(0.3 + random(runtime) * 0.35),
  }));
  const multiFocusFeatures = gmMultiFocusToMultiFocusFeatures(focusTargets);
  const chosenAction = actions[chosenIndex] ?? actions[0];
  const trajectoryFeatures = gmHistoryToTrajectoryFeatures({ events: worldState.events });
  const policyScores = scoreGMActions(runtime, worldState, actions);
  const attentionWeights = normalizeWeights(focusTargets.map(target => target.severity ?? 0.25));
  const quality = clamp01(
    (chosenAction?.type === 'dialogue' ? 0.83 : chosenAction?.type === 'combat_action' ? 0.76 : 0.7) +
    (worldState.flags.combatActive && chosenAction?.type === 'combat_action' ? 0.08 : 0) -
    (chosenIndex === 0 ? 0.02 : 0)
  );

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'planning',
    domain: 'gm',
    organ: 'policy_prior',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { policyScores, attentionWeights },
    decision: chosenAction,
    outcome: { quality },
    trajectoryFeatures,
    replay: replay(runtime, `gm-${sessionIndex}-policy-prior`, sessionIndex, 'gm', 'policy_prior', 'planning'),
  });

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'planning',
    domain: 'gm',
    organ: 'attention',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { attentionWeights },
    decision: chosenAction,
    outcome: { quality },
    trajectoryFeatures,
    replay: replay(runtime, `gm-${sessionIndex}-attention`, sessionIndex, 'gm', 'attention', 'planning'),
  });

  appendTraceEntry({
    sessionId,
    timestamp: timestamp(sessionIndex),
    phase: 'output',
    domain: 'gm',
    organ: 'risk_outcome',
    stateFeatures,
    actionFeatures,
    multiFocusFeatures,
    chosenActionIndex: chosenIndex,
    organOutputs: { attentionWeights },
    decision: chosenAction,
    outcome: {
      quality,
      coherence: clamp01(0.5 + (chosenAction?.type === 'dialogue' ? 0.35 : 0.08)),
      tension: clamp01(worldState.combat.active ? 0.8 : 0.35),
      engagement: clamp01(chosenAction?.type === 'escalate' ? 0.55 : 0.82),
      metrics: {
        coherence: clamp01(0.5 + (chosenAction?.type === 'dialogue' ? 0.35 : 0.08)),
        tension: clamp01(worldState.combat.active ? 0.8 : 0.35),
        engagement: clamp01(chosenAction?.type === 'escalate' ? 0.55 : 0.82),
      },
    },
    trajectoryFeatures,
    replay: replay(runtime, `gm-${sessionIndex}-risk-outcome`, sessionIndex, 'gm', 'risk_outcome', 'output'),
  });
}

export async function runTrainingSessions() {
  console.log('Starting training sessions...');

  const sessionsPerDomain = 8;
  const seed = readTraceSeed();
  const runtime: TraceRuntime = { rng: new SeededRng(seed), seed, step: 0 };
  console.log(`Using replayable organ trace seed ${seed}.`);

  console.log('Running GM sessions...');
  for (let i = 0; i < sessionsPerDomain; i++) {
    const gmCore = new SynthesusCoreStub();
    const input: CoreInput = {
      query: `GM training turn ${i}`,
      domain: 'gm',
      sessionId: `gm-session-${i}`,
    };
    const worldState = buildGMWorldState(runtime, i);
    const candidateActions = buildGMActions(i);
    const chosenIndex = chooseWeightedIndex(runtime, scoreGMActions(runtime, worldState, candidateActions), 0.25);
    const intakeResult = await gmCore.intake({ ...input, worldState });
    const planResult = await gmCore.plan(intakeResult.worldState);
    const actionResult = await gmCore.act(planResult);
    logGmTrace(runtime, input.sessionId, worldState, candidateActions, chosenIndex, i);
    void actionResult;
  }

  console.log('Running SysOps sessions...');
  for (let i = 0; i < sessionsPerDomain; i++) {
    const sysOpsCore = new SynthesusCoreSysOps();
    const input: CoreInput = {
      query: `SysOps training turn ${i}`,
      domain: 'sysops',
      sessionId: `sysops-session-${i}`,
    };
    const worldState = buildSysOpsWorldState(runtime, i);
    const candidateActions = buildSysOpsActions(i);
    const chosenIndex = chooseWeightedIndex(runtime, scoreSysOpsActions(runtime, worldState, candidateActions), 0.25);
    const intakeResult = await sysOpsCore.intake({ ...input, worldState });
    const planResult = await sysOpsCore.plan(intakeResult.worldState);
    const actionResult = await sysOpsCore.act(planResult);
    logSysOpsTrace(runtime, input.sessionId, worldState, candidateActions, chosenIndex, i);
    void actionResult;
  }

  console.log('Running Chat sessions...');
  for (let i = 0; i < sessionsPerDomain; i++) {
    const chatCore = new SynthesusCoreChat();
    const input: CoreInput = {
      query: `Chat training turn ${i}`,
      domain: 'chat',
      sessionId: `chat-session-${i}`,
    };
    const worldState = buildChatWorldState(runtime, i);
    const candidateActions = buildChatActions(i);
    const chosenIndex = chooseWeightedIndex(runtime, scoreChatActions(runtime, worldState, candidateActions), 0.25);
    const intakeResult = await chatCore.intake({ ...input, worldState });
    const planResult = await chatCore.plan(intakeResult.worldState);
    const actionResult = await chatCore.act(planResult);
    logChatTrace(runtime, input.sessionId, worldState, candidateActions, chosenIndex, i);
    void actionResult;
  }

  console.log('Training sessions completed. Logs collected.');
}
