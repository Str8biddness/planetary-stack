import { PredictionOrgan } from '../packages/organs/shared/PredictionOrgan';
import { ForecastOrgan } from '../packages/organs/shared/ForecastOrgan';
import { SequencePredictionOrgan } from '../packages/organs/shared/SequencePredictionOrgan';
import { RelationOrgan } from '../packages/organs/shared/RelationOrgan';
import { StateFeatures } from '../packages/core/amplification/features';
import { OrganContext } from '../packages/organs/registry';

describe('Shared ML Organs', () => {
  const mockContext: OrganContext = {
    userId: 'test_user',
    characterId: 'test_char',
    sessionId: 'test_session',
    computeBudget: 10,
    timestamp: Date.now(),
  };

  const mockInput: StateFeatures = {
    dense: [0.1, 0.2, 0.3],
    sparse: {
      criticalIncidents: 0,
      unresolvedQuestions: 1,
      confusion: 0.1,
      frustration: 0.05,
      avgServiceLatency: 100,
    },
  };

  describe('PredictionOrgan', () => {
    it('should generate a valid prediction', async () => {
      const organ = new PredictionOrgan();
      const output = await organ.predict(mockInput, mockContext);
      
      expect(output).toBeDefined();
      expect(typeof output.predictionScore).toBe('number');
      expect(typeof output.confidence).toBe('number');
      expect(['up', 'down', 'flat']).toContain(output.direction);
      expect(Array.isArray(output.signals)).toBe(true);
      expect(typeof output.summary).toBe('string');
    });

    it('should react to critical incidents', async () => {
      const organ = new PredictionOrgan();
      const incidentInput: StateFeatures = {
        ...mockInput,
        sparse: {
          ...mockInput.sparse,
          criticalIncidents: 5,
        },
      };
      const output = await organ.predict(incidentInput, mockContext);
      expect(output.signals).toContain('critical_incidents');
    });
  });

  describe('ForecastOrgan', () => {
    it('should generate a valid forecast', async () => {
      const organ = new ForecastOrgan();
      const output = await organ.predict(mockInput, mockContext);
      
      expect(output).toBeDefined();
      expect(typeof output.horizon).toBe('string');
      expect(['rising', 'falling', 'stable']).toContain(output.trend);
      expect(typeof output.summary).toBe('string');
    });
  });

  describe('SequencePredictionOrgan', () => {
    it('should generate a valid sequence prediction', async () => {
      const organ = new SequencePredictionOrgan();
      const output = await organ.predict({
        stateFeatures: mockInput,
        trajectoryFeatures: {
          dense: [0.1],
          sparse: { resolution: 0.5, stability: 0.8, turnBalance: 0.5, confusionRate: 0.1, incidentRate: 0, actionRate: 0.2 }
        }
      }, mockContext);
      
      expect(output).toBeDefined();
      expect(typeof output.sequenceScore).toBe('number');
      expect(typeof output.expectedContinuity).toBe('number');
      expect(typeof output.expectedChurn).toBe('number');
    });
  });

  describe('RelationOrgan', () => {
    it('should generate a valid relation analysis', async () => {
      const organ = new RelationOrgan();
      const output = await organ.predict(mockInput, mockContext);
      
      expect(output).toBeDefined();
      expect(typeof output.relationScore).toBe('number');
      expect(typeof output.trust).toBe('number');
      expect(typeof output.rapport).toBe('number');
      expect(typeof output.conflict).toBe('number');
      expect(typeof output.summary).toBe('string');
    });
  });
});
