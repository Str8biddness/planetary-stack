// tests/domains/gm/featureAdapters.test.ts
// Unit tests for GM domain feature adapters

import {
  gmStateToStateFeatures,
  gmActionToActionFeatures,
  gmHistoryToTrajectoryFeatures,
  gmMultiFocusToMultiFocusFeatures,
} from '../../../domains/gm/featureAdapters';
import { GMWorldState, GMAction, GMHistory, GMFocusTarget } from '../../../domains/gm/types';

describe('GM Feature Adapters', () => {
  const mockWorldState: GMWorldState = {
    domain: 'gm',
    tick: 100,
    location: 'dungeon_room_1',
    npcs: [
      { id: 'npc1', name: 'Goblin', health: 0.8, disposition: 'hostile', location: 'dungeon_room_1', state: 'combat', tags: ['goblin', 'monster'] },
      { id: 'npc2', name: 'Skeleton', health: 0.5, disposition: 'hostile', location: 'dungeon_room_1', state: 'idle', tags: ['undead'] },
    ],
    combat: {
      active: true,
      participants: ['npc1', 'npc2'],
      round: 3,
      playerHealth: 0.75,
      enemiesVisible: 2,
      lastAction: 'attack',
    },
    events: [],
    flags: {
      combatActive: true,
      playerLowHealth: false,
      escalation: false,
    },
    timestamp: new Date(),
  };

  describe('gmStateToStateFeatures', () => {
    it('should convert GM world state to dense features', () => {
      const features = gmStateToStateFeatures(mockWorldState);

      expect(features.dense).toHaveLength(7);
      expect(features.dense[0]).toBe(2 / 20); // npc count normalized
      expect(features.dense[1]).toBe(1); // combat active
      expect(features.dense[2]).toBe(0.75); // player health
      expect(features.dense[3]).toBe(2); // enemies visible
      expect(features.dense[4]).toBe(100 / 1000); // tick normalized
    });

    it('should create correct sparse features', () => {
      const features = gmStateToStateFeatures(mockWorldState);

      expect(features.sparse.npcCount).toBe(2);
      expect(features.sparse.combatActive).toBe(1);
      expect(features.sparse.playerHealth).toBe(0.75);
      expect(features.sparse.enemiesVisible).toBe(2);
      expect(features.sparse.location).toBe('dungeon_room_1');
    });

    it('should handle empty world state gracefully', () => {
      const emptyState: GMWorldState = {
        domain: 'gm',
        tick: 0,
        location: '',
        npcs: [],
        combat: { active: false, participants: [], round: 0, playerHealth: 1, enemiesVisible: 0 },
        events: [],
        flags: { combatActive: false, playerLowHealth: false, escalation: false },
        timestamp: new Date(),
      };

      const features = gmStateToStateFeatures(emptyState);

      expect(features.dense[0]).toBe(0);
      expect(features.dense[1]).toBe(0);
      expect(features.sparse.npcCount).toBe(0);
    });
  });

  describe('gmActionToActionFeatures', () => {
    it('should convert spawn_npc action to features', () => {
      const action: GMAction = {
        type: 'spawn_npc',
        description: 'Spawn a goblin',
        target: 'goblin_1',
      };

      const features = gmActionToActionFeatures(mockWorldState, action);

      expect(features.dense[0]).toBe(1); // spawn_npc
      expect(features.dense[5]).toBe(0); // not escalate
      expect(features.sparse.actionType).toBe('spawn_npc');
      expect(features.sparse.target).toBe('goblin_1');
    });

    it('should convert combat_action to features during combat', () => {
      const action: GMAction = {
        type: 'combat_action',
        description: 'Attack with sword',
      };

      const features = gmActionToActionFeatures(mockWorldState, action);

      expect(features.dense[3]).toBe(1); // combat_action
      expect(features.sparse.inCombat).toBe(1);
    });

    it('should mark escalate action correctly', () => {
      const action: GMAction = {
        type: 'escalate',
        description: 'Call reinforcements',
      };

      const features = gmActionToActionFeatures(mockWorldState, action);

      expect(features.dense[5]).toBe(1); // escalate
    });
  });

  describe('gmHistoryToTrajectoryFeatures', () => {
    it('should convert event history to trajectory features', () => {
      const history: GMHistory = {
        events: [
          { timestamp: new Date(), type: 'combat_start', details: {} },
          { timestamp: new Date(), type: 'npc_tick', details: {} },
          { timestamp: new Date(), type: 'npc_tick', details: {} },
          { timestamp: new Date(), type: 'spawn', details: {} },
        ],
      };

      const features = gmHistoryToTrajectoryFeatures(history);

      expect(features.dense[0]).toBe(4); // total events
      expect(features.dense[1]).toBe(1); // spawns
      expect(features.dense[2]).toBe(1); // combats
      expect(features.dense[3]).toBe(2); // npc_ticks
    });

    it('should handle empty history', () => {
      const history: GMHistory = { events: [] };

      const features = gmHistoryToTrajectoryFeatures(history);

      expect(features.dense[0]).toBe(0);
      expect(features.sparse.spawnRate).toBe(0);
    });

    it('should calculate correct rates', () => {
      const history: GMHistory = {
        events: Array(10).fill(null).map((_, i) => ({
          timestamp: new Date(),
          type: i < 3 ? 'spawn' : 'npc_tick',
          details: {},
        })),
      };

      const features = gmHistoryToTrajectoryFeatures(history);

      expect(features.sparse.spawnRate).toBe(0.3); // 3/10
      expect(features.sparse.npcTickRate).toBe(0.7); // 7/10
    });
  });

  describe('gmMultiFocusToMultiFocusFeatures', () => {
    it('should convert focus targets to multi-focus features', () => {
      const targets: GMFocusTarget[] = [
        { id: 'npc1', type: 'npc', severity: 0.8, recency: 0.9, connectivity: 0.7 },
        { id: 'combat1', type: 'combat', severity: 1.0, recency: 1.0, connectivity: 0.9 },
      ];

      const features = gmMultiFocusToMultiFocusFeatures(targets);

      expect(features.targets).toHaveLength(2);
      expect(features.targets[0].dense).toHaveLength(3);
      expect(features.targets[0].dense[0]).toBe(0.8); // severity
      expect(features.targets[0].dense[1]).toBe(0.9); // recency
      expect(features.targets[0].dense[2]).toBe(0.7); // connectivity
    });

    it('should handle empty targets', () => {
      const features = gmMultiFocusToMultiFocusFeatures([]);

      expect(features.targets).toHaveLength(0);
    });

    it('should include sparse features per target', () => {
      const targets: GMFocusTarget[] = [
        { id: 'npc1', type: 'npc', severity: 0.5, recency: 0.6, connectivity: 0.4 },
      ];

      const features = gmMultiFocusToMultiFocusFeatures(targets);

      expect(features.targets[0].id).toBe('npc1');
      expect(features.targets[0].sparse.type).toBe('npc');
      expect(features.targets[0].sparse.severity).toBe(0.5);
    });
  });
});
