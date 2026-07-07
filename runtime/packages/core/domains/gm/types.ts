// domains/gm/types.ts
// GM (Game Master / world-simulation) domain types for Synthesus 3.0

export interface GMNpc {
  id: string;
  name: string;
  health: number; // 0-1
  disposition: 'friendly' | 'neutral' | 'hostile';
  location: string;
  state: 'idle' | 'combat' | 'fleeing' | 'dead';
  tags: string[];
}

export interface GMCombat {
  active: boolean;
  participants: string[]; // npc ids
  round: number;
  playerHealth: number; // 0-1
  enemiesVisible: number;
  lastAction?: string;
}

export interface GMWorldEvent {
  timestamp: Date;
  type: 'spawn' | 'combat_start' | 'combat_end' | 'npc_tick' | 'player_action' | 'env_change';
  details: Record<string, any>;
}

export interface GMWorldState {
  domain: string;
  tick: number;
  location: string;
  npcs: GMNpc[];
  combat: GMCombat;
  events: GMWorldEvent[];
  flags: {
    combatActive: boolean;
    playerLowHealth: boolean;
    escalation: boolean;
  };
  timestamp: Date;
}

export interface GMAction {
  type: 'spawn_npc' | 'tick_world' | 'move_character' | 'combat_action' | 'dialogue' | 'escalate';
  target?: string; // npc id or location
  parameters?: Record<string, any>;
  description: string;
}

export interface GMHistory {
  events: GMWorldEvent[];
  summary?: string;
}

export interface GMFocusTarget {
  id: string;
  type: 'npc' | 'location' | 'combat' | 'event';
  severity?: number; // 0-1
  recency?: number; // 0-1
  connectivity?: number; // 0-1 importance to player/narrative
}

export interface GMInput {
  sessionId: string;
  query: string;
  worldState?: GMWorldState;
}

export interface GMOutput {
  action: GMAction;
  narrative: string;
  updatedWorld: GMWorldState;
}
