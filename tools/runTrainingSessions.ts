// scripts/runTrainingSessions.ts
// Script to run amplified sessions in GM, SysOps, Chat domains and emit diverse training traces

import { SynthesusCoreStub, CoreInput } from '../synthetic_core/index';
import { SynthesusCoreSysOps } from '../synthetic_core/synthesusCoreSysOps';
import { SynthesusCoreChat } from '../synthetic_core/synthesusCoreChat';
import { appendTraceEntry } from '../learning/teacherTrace';
import { chatStateToStateFeatures, chatActionToActionFeatures, chatHistoryToTrajectoryFeatures, chatMultiFocusToMultiFocusFeatures } from '../domains/chat/featureAdapters';
import { sysStateToStateFeatures, sysActionToActionFeatures, sysHistoryToTrajectoryFeatures, sysMultiFocusToMultiFocusFeatures } from '../domains/sysops/featureAdapters';
import { gmStateToStateFeatures, gmActionToActionFeatures, gmHistoryToTrajectoryFeatures, gmMultiFocusToMultiFocusFeatures } from '../domains/gm/featureAdapters';
import { ChatWorldState, ChatAction, ChatFocusTarget } from '../domains/chat/types';
import { SysWorldState, SysAction, SysFocusTarget } from '../domains/sysops/types';
import { GMWorldState, GMAction, GMFocusTarget } from '../domains/gm/types';

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

function jitter(value: number, magnitude = 0.18): number {
  return clamp01(value + (Math.random() - 0.5) * magnitude);
}

function chooseWeightedIndex(weights: number[], suboptimalChance = 0.2): number {
  if (weights.length === 0) return 0;
  const ranked = weights
    .map((score, idx) => ({ score, idx }))
    .sort((a, b) => b.score - a.score);

  if (weights.length > 1 && Math.random() < suboptimalChance) {
    const alternatives = ranked.slice(1);
    return alternatives[Math.floor(Math.random() * alternatives.length)]?.idx ?? ranked[0].idx;
  }

  const total = weights.reduce((sum, value) => sum + Math.max(0, value), 0);
  if (total <= 0) return ranked[0].idx;

  let cursor = Math.random() * total;
  for (const { score, idx } of ranked) {
    cursor -= Math.max(0, score);
    if (cursor <= 0) return idx;
  }
  return ranked[0].idx;
}

function buildChatWorldState(sessionIndex: number): ChatWorldState {
  const mood = sessionIndex % 4;
  const flags = {
    confusion: mood === 0 || Math.random() < 0.25,
    safety: mood === 3 || Math.random() < 0.15,
    frustration: mood === 1 || Math.random() < 0.2,
  };
  const history = [
    {
      speaker: 'user' as const,
      message: mood === 0 ? 'I am not sure what to do.' : 'Can you help me with this?',
      timestamp: new Date(Date.now() - 3_600_000),
    },
    {
      speaker: 'system' as const,
      message: mood === 2 ? 'Here is a summary so far.' : 'What is the core constraint?',
      timestamp: new Date(Date.now() - 1_800_000),
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
    timestamp: new Date(),
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

function scoreChatActions(worldState: ChatWorldState, actions: ChatAction[]): number[] {
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
  }).map(score => jitter(score, 0.24)));
}

function logChatTrace(sessionId: string, worldState: ChatWorldState, actions: ChatAction[], chosenIndex: number): void {
  const stateFeatures = chatStateToStateFeatures(worldState);
  const actionFeatures = actions.map(action => chatActionToActionFeatures(worldState, action));
  const focusTargets: ChatFocusTarget[] = actions.map((action, idx) => ({
    id: `${action.type}-${idx}`,
    type: 'goal',
    importance: clamp01(0.35 + (idx === chosenIndex ? 0.4 : 0.1) + Math.random() * 0.15),
    urgency: action.type === 'ask_clarification' ? 1 : action.type === 'answer_question' ? 0.8 : 0.45,
    lastMentioned: new Date(Date.now() - Math.floor(Math.random() * 3) * 86_400_000),
  }));
  const multiFocusFeatures = chatMultiFocusToMultiFocusFeatures(focusTargets);
  const chosenAction = actions[chosenIndex] ?? actions[0];
  const trajectoryFeatures = chatHistoryToTrajectoryFeatures({ turns: worldState.history });
  const policyScores = scoreChatActions(worldState, actions);
  const attentionWeights = normalizeWeights(focusTargets.map(target => target.importance));
  const quality = clamp01(
    (chosenAction?.type === 'answer_question' ? 0.92 : chosenAction?.type === 'summarize' ? 0.82 : 0.7) +
    (worldState.flags.confusion && chosenAction?.type === 'ask_clarification' ? 0.08 : 0) -
    (chosenIndex === 0 ? 0.03 : 0)
  );

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });
}

function buildSysOpsWorldState(sessionIndex: number): SysWorldState {
  const hostCount = 2 + (sessionIndex % 3);
  const serviceCount = 2 + (sessionIndex % 2);
  const hosts = Array.from({ length: hostCount }, (_, idx) => ({
    id: `host-${sessionIndex}-${idx}`,
    health: clamp01(0.55 + Math.random() * 0.4 - (idx === 0 && sessionIndex % 2 === 0 ? 0.25 : 0)),
    errorRate: clamp01(Math.random() * 0.35 + (idx === 0 ? 0.08 : 0.02)),
    latency: 80 + Math.random() * 120,
    saturation: clamp01(0.3 + Math.random() * 0.6),
    lastRestart: Math.random() < 0.3 ? new Date(Date.now() - 86_400_000) : undefined,
  }));
  const services = Array.from({ length: serviceCount }, (_, idx) => ({
    name: `service-${sessionIndex}-${idx}`,
    health: clamp01(0.6 + Math.random() * 0.35 - (idx === 1 && sessionIndex % 3 === 0 ? 0.2 : 0)),
    dependencies: idx === 0 ? ['auth'] : ['api', 'db'],
    errorRate: clamp01(Math.random() * 0.25),
    latency: 100 + Math.random() * 220,
    lastDeploy: Math.random() < 0.4 ? new Date(Date.now() - 2 * 86_400_000) : undefined,
  }));
  const incidents = [] as SysWorldState['incidents'];
  if (sessionIndex % 2 === 0) {
    incidents.push({
      id: `incident-${sessionIndex}-0`,
      severity: sessionIndex % 4 === 0 ? 'critical' : 'high',
      startTime: new Date(Date.now() - 2 * 3_600_000),
      duration: 7200,
      services: [services[0].name],
      blastRadius: clamp01(0.4 + Math.random() * 0.4),
      status: sessionIndex % 4 === 0 ? 'open' : 'mitigating',
    });
  }
  if (sessionIndex % 3 === 1) {
    incidents.push({
      id: `incident-${sessionIndex}-1`,
      severity: 'medium',
      startTime: new Date(Date.now() - 5 * 3_600_000),
      duration: 1800,
      services: [services[1]?.name ?? services[0].name],
      blastRadius: clamp01(0.2 + Math.random() * 0.3),
      status: 'resolved',
    });
  }
  return {
    domain: 'sysops',
    hosts,
    services,
    incidents,
    alerts: sessionIndex % 2 === 0 ? ['latency spike', 'error burst'] : ['routine drift'],
    timestamp: new Date(),
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

function scoreSysOpsActions(worldState: SysWorldState, actions: SysAction[]): number[] {
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
  }).map(score => jitter(score, 0.26)));
}

function logSysOpsTrace(sessionId: string, worldState: SysWorldState, actions: SysAction[], chosenIndex: number): void {
  const stateFeatures = sysStateToStateFeatures(worldState);
  const actionFeatures = actions.map(action => sysActionToActionFeatures(worldState, action));
  const focusTargets: SysFocusTarget[] = actions.map((action, idx) => ({
    id: `${action.target}-${idx}`,
    type: 'service',
    severity: clamp01(0.4 + (idx === chosenIndex ? 0.45 : 0.12) + Math.random() * 0.1),
    recency: clamp01(0.4 + Math.random() * 0.3),
    connectivity: clamp01(0.35 + Math.random() * 0.3),
  }));
  const multiFocusFeatures = sysMultiFocusToMultiFocusFeatures(focusTargets);
  const chosenAction = actions[chosenIndex] ?? actions[0];
  const trajectoryFeatures = sysHistoryToTrajectoryFeatures({ events: worldState.incidents.map(incident => ({
    timestamp: incident.startTime,
    type: 'incident',
    details: { severity: incident.severity, status: incident.status, services: incident.services },
  })).concat(worldState.hosts.slice(0, 1).map(host => ({
    timestamp: new Date(),
    type: 'action',
    details: { type: 'restart', target: host.id },
  }))) });
  const policyScores = scoreSysOpsActions(worldState, actions);
  const attentionWeights = normalizeWeights(focusTargets.map(target => target.severity ?? 0.25));
  const quality = clamp01(
    (chosenAction?.type === 'runbook' ? 0.9 : chosenAction?.type === 'failover' ? 0.84 : 0.72) +
    (worldState.incidents.some(incident => incident.severity === 'critical') && chosenAction?.type === 'runbook' ? 0.05 : 0) -
    (chosenIndex === 0 ? 0.02 : 0)
  );

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });
}

function buildGMWorldState(sessionIndex: number): GMWorldState {
  const combatActive = sessionIndex % 2 === 0;
  const npcs = Array.from({ length: 2 + (sessionIndex % 3) }, (_, idx) => ({
    id: `npc-${sessionIndex}-${idx}`,
    name: `NPC ${sessionIndex}-${idx}`,
    health: clamp01(0.55 + Math.random() * 0.4 - (combatActive && idx === 0 ? 0.15 : 0)),
    disposition: idx === 0 && combatActive ? 'hostile' : idx === 1 ? 'friendly' : 'neutral',
    location: idx === 0 ? 'town-square' : 'market',
    state: combatActive && idx === 0 ? 'combat' : 'idle',
    tags: combatActive ? ['combat', 'urgent'] : ['dialogue', 'lore'],
  }));
  const events = [
    {
      timestamp: new Date(Date.now() - 3_600_000),
      type: 'player_action' as const,
      details: { action: combatActive ? 'attacked' : 'talked' },
    },
    {
      timestamp: new Date(Date.now() - 1_800_000),
      type: combatActive ? 'combat_start' as const : 'env_change' as const,
      details: { intensity: combatActive ? 'high' : 'medium' },
    },
  ];
  if (sessionIndex % 3 === 0) {
    events.push({
      timestamp: new Date(Date.now() - 900_000),
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
      playerHealth: clamp01(0.6 + Math.random() * 0.4 - (combatActive ? 0.2 : 0)),
      enemiesVisible: combatActive ? 2 + (sessionIndex % 2) : 0,
      lastAction: combatActive ? 'attack' : 'dialogue',
    },
    events,
    flags: {
      combatActive,
      playerLowHealth: combatActive && sessionIndex % 3 === 0,
      escalation: sessionIndex % 4 === 0,
    },
    timestamp: new Date(),
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

function scoreGMActions(worldState: GMWorldState, actions: GMAction[]): number[] {
  return normalizeWeights(actions.map(action => {
    if (action.type === 'dialogue') return worldState.combat.active ? 0.45 : 0.9;
    if (action.type === 'combat_action') return worldState.combat.active ? 0.92 : 0.4;
    if (action.type === 'escalate') return worldState.flags.escalation ? 0.88 : 0.35;
    return 0.2;
  }).map(score => jitter(score, 0.25)));
}

function logGmTrace(sessionId: string, worldState: GMWorldState, actions: GMAction[], chosenIndex: number): void {
  const stateFeatures = gmStateToStateFeatures(worldState);
  const actionFeatures = actions.map(action => gmActionToActionFeatures(worldState, action));
  const focusTargets: GMFocusTarget[] = actions.map((action, idx) => ({
    id: `${action.type}-${idx}`,
    type: 'npc',
    severity: clamp01(0.35 + (idx === chosenIndex ? 0.45 : 0.1) + Math.random() * 0.15),
    recency: clamp01(0.3 + Math.random() * 0.4),
    connectivity: clamp01(0.3 + Math.random() * 0.35),
  }));
  const multiFocusFeatures = gmMultiFocusToMultiFocusFeatures(focusTargets);
  const chosenAction = actions[chosenIndex] ?? actions[0];
  const trajectoryFeatures = gmHistoryToTrajectoryFeatures({ events: worldState.events });
  const policyScores = scoreGMActions(worldState, actions);
  const attentionWeights = normalizeWeights(focusTargets.map(target => target.severity ?? 0.25));
  const quality = clamp01(
    (chosenAction?.type === 'dialogue' ? 0.83 : chosenAction?.type === 'combat_action' ? 0.76 : 0.7) +
    (worldState.flags.combatActive && chosenAction?.type === 'combat_action' ? 0.08 : 0) -
    (chosenIndex === 0 ? 0.02 : 0)
  );

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });

  appendTraceEntry({
    sessionId,
    timestamp: new Date(),
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
  });
}

export async function runTrainingSessions() {
  console.log('Starting training sessions...');

  const sessionsPerDomain = 8;

  console.log('Running GM sessions...');
  for (let i = 0; i < sessionsPerDomain; i++) {
    const gmCore = new SynthesusCoreStub();
    const input: CoreInput = {
      query: `GM training turn ${i}`,
      domain: 'gm',
      sessionId: `gm-session-${i}`,
    };
    const worldState = buildGMWorldState(i);
    const candidateActions = buildGMActions(i);
    const chosenIndex = chooseWeightedIndex(scoreGMActions(worldState, candidateActions), 0.25);
    const intakeResult = await gmCore.intake({ ...input, worldState });
    const planResult = await gmCore.plan(intakeResult.worldState);
    const actionResult = await gmCore.act(planResult);
    logGmTrace(input.sessionId, worldState, candidateActions, chosenIndex);
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
    const worldState = buildSysOpsWorldState(i);
    const candidateActions = buildSysOpsActions(i);
    const chosenIndex = chooseWeightedIndex(scoreSysOpsActions(worldState, candidateActions), 0.25);
    const intakeResult = await sysOpsCore.intake({ ...input, worldState });
    const planResult = await sysOpsCore.plan(intakeResult.worldState);
    const actionResult = await sysOpsCore.act(planResult);
    logSysOpsTrace(input.sessionId, worldState, candidateActions, chosenIndex);
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
    const worldState = buildChatWorldState(i);
    const candidateActions = buildChatActions(i);
    const chosenIndex = chooseWeightedIndex(scoreChatActions(worldState, candidateActions), 0.25);
    const intakeResult = await chatCore.intake({ ...input, worldState });
    const planResult = await chatCore.plan(intakeResult.worldState);
    const actionResult = await chatCore.act(planResult);
    logChatTrace(input.sessionId, worldState, candidateActions, chosenIndex);
    void actionResult;
  }

  console.log('Training sessions completed. Logs collected.');
}
