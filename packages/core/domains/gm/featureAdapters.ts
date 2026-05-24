// domains/gm/featureAdapters.ts
// GM feature adapters mapping domain data to generic feature views for Synthesus 3.0

import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from '../../amplification/features';
import { GMWorldState, GMAction, GMHistory, GMFocusTarget } from './types';
import { toNumber } from '../../utils/normalization';

export function gmStateToStateFeatures(state: GMWorldState): StateFeatures {
  const dense: number[] = [
    (state.npcs || []).length / 20,
    state.combat?.active ? 1 : 0,
    state.combat?.playerHealth ?? 1.0,
    state.combat?.enemiesVisible ?? 0,
    state.tick / 1000,
    state.flags?.playerLowHealth ? 1 : 0,
    state.flags?.escalation ? 1 : 0,
  ];
  const sparse: Record<string, number | string> = {
    npcCount: (state.npcs || []).length,
    combatActive: state.combat?.active ? 1 : 0,
    playerHealth: state.combat?.playerHealth ?? 1.0,
    enemiesVisible: state.combat?.enemiesVisible ?? 0,
    location: state.location || 'unknown',
    escalation: state.flags?.escalation ? 1 : 0,
  };
  return { dense, sparse };
}

export function gmActionToActionFeatures(state: GMWorldState, action: GMAction): ActionFeatures {
  const dense: number[] = [
    action.type === 'spawn_npc' ? 1 : 0,
    action.type === 'tick_world' ? 1 : 0,
    action.type === 'move_character' ? 1 : 0,
    action.type === 'combat_action' ? 1 : 0,
    action.type === 'dialogue' ? 1 : 0,
    action.type === 'escalate' ? 1 : 0,
  ];
  const sparse: Record<string, number | string> = {
    actionType: action.type,
    target: action.target || 'none',
    inCombat: state.combat?.active ? 1 : 0,
  };
  return { dense, sparse };
}

export function gmHistoryToTrajectoryFeatures(history: GMHistory): TrajectoryFeatures {
  const events = history.events || [];
  const spawns = events.filter(e => e.type === 'spawn').length;
  const combats = events.filter(e => e.type === 'combat_start' || e.type === 'combat_end').length;
  const npcTicks = events.filter(e => e.type === 'npc_tick').length;
  const dense: number[] = [
    events.length,
    spawns,
    combats,
    npcTicks,
    combats / Math.max(1, events.length),
  ];
  const sparse: Record<string, number | string> = {
    spawnRate: spawns / Math.max(1, events.length),
    combatRate: combats / Math.max(1, events.length),
    npcTickRate: npcTicks / Math.max(1, events.length),
  };
  return { dense, sparse };
}

export function gmMultiFocusToMultiFocusFeatures(targets: GMFocusTarget[]): MultiFocusFeatures {
  const mappedTargets = targets.map(t => ({
    id: t.id,
    dense: [
      toNumber(t.severity),
      toNumber(t.recency),
      toNumber(t.connectivity),
    ],
    sparse: {
      type: t.type,
      severity: toNumber(t.severity),
      recency: toNumber(t.recency),
      connectivity: toNumber(t.connectivity),
    },
  }));
  return { targets: mappedTargets };
}
