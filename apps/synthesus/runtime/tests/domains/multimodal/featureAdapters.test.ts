// tests/domains/multimodal/featureAdapters.test.ts
// Unit tests for multimodal domain feature adapters

import {
  multimodalStateToStateFeatures,
  multimodalActionToActionFeatures,
  multimodalHistoryToTrajectoryFeatures,
  multimodalMultiFocusToMultiFocusFeatures,
} from '../../../domains/multimodal/featureAdapters';
import {
  MultimodalWorldState,
  MultimodalAction,
  MultimodalTurn,
  MultimodalFocusTarget,
  AlignmentState,
} from '../../../domains/multimodal/types';

describe('Multimodal Feature Adapters', () => {
  const mockAlignment: AlignmentState = {
    confidence: 0.85,
    modalityWeights: {
      vision: 0.4,
      voice: 0.35,
      text: 0.25,
    },
    visionTextScore: 0.8,
    voiceTextScore: 0.75,
    visionVoiceScore: 0.7,
  };

  const mockWorldState: MultimodalWorldState = {
    domain: 'multimodal',
    sessionId: 'test-session',
    timestamp: new Date(),
    vision: {
      width: 1920,
      height: 1080,
      mimeType: 'image/jpeg',
      timestamp: new Date(),
      features: {
        objects: [
          { label: 'person', confidence: 0.95, bbox: [0.1, 0.2, 0.3, 0.4] },
          { label: 'chair', confidence: 0.8, bbox: [0.5, 0.6, 0.1, 0.2] },
        ],
        scene: { primary: 'indoor', confidence: 0.9, context: ['office', 'workspace'] },
      },
    },
    voice: {
      duration: 5.0,
      sampleRate: 16000,
      channels: 1,
      mimeType: 'audio/wav',
      timestamp: new Date(),
      transcript: { text: 'Hello there', confidence: 0.92, isFinal: true },
      acoustic: { pitch: 150, energy: 0.7, speakingRate: 3.5 },
    },
    text: {
      content: 'What do you see in this image?',
      language: 'en',
      tokens: 7,
      timestamp: new Date(),
    },
    alignment: mockAlignment,
    history: [],
    context: {},
  };

  describe('multimodalStateToStateFeatures', () => {
    it('should convert multimodal world state to dense features', () => {
      const features = multimodalStateToStateFeatures(mockWorldState);

      expect(features.dense).toHaveLength(15);
      expect(features.dense[0]).toBe(1); // hasVision
      expect(features.dense[1]).toBe(1); // hasVoice
      expect(features.dense[2]).toBe(1); // hasText
      expect(features.dense[3]).toBe(0.85); // confidence
      expect(features.dense[4]).toBe(0.8); // visionTextScore
      expect(features.dense[5]).toBe(0.75); // voiceTextScore
      expect(features.dense[6]).toBe(0.7); // visionVoiceScore
      expect(features.dense[7]).toBe(0.4); // vision weight
      expect(features.dense[8]).toBe(0.35); // voice weight
      expect(features.dense[9]).toBe(0.25); // text weight
    });

    it('should create correct sparse features', () => {
      const features = multimodalStateToStateFeatures(mockWorldState);

      expect(features.sparse.hasVision).toBe(1);
      expect(features.sparse.hasVoice).toBe(1);
      expect(features.sparse.hasText).toBe(1);
      expect(features.sparse.visionConfidence).toBe(0.9);
      expect(features.sparse.voiceConfidence).toBe(0.92);
      expect(features.sparse.textTokens).toBe(7);
      expect(features.sparse.dominantModality).toBe('vision');
    });

    it('should handle missing modalities', () => {
      const partialState: MultimodalWorldState = {
        ...mockWorldState,
        vision: undefined,
        voice: undefined,
        alignment: {
          ...mockAlignment,
          modalityWeights: { vision: 0, voice: 0, text: 1.0 },
        },
      };

      const features = multimodalStateToStateFeatures(partialState);

      expect(features.dense[0]).toBe(0); // no vision
      expect(features.dense[1]).toBe(0); // no voice
      expect(features.dense[2]).toBe(1); // has text
      expect(features.sparse.dominantModality).toBe('text');
    });

    it('should calculate alignment score correctly', () => {
      const features = multimodalStateToStateFeatures(mockWorldState);

      // Average of three alignment scores
      const expectedAlignment = (0.8 + 0.75 + 0.7) / 3;
      expect(features.sparse?.alignmentScore).toBeCloseTo(expectedAlignment, 2);
    });
  });

  describe('multimodalActionToActionFeatures', () => {
    it('should convert respond_text action to features', () => {
      const action: MultimodalAction = {
        type: 'respond_text',
        description: 'Respond with text only',
        responseConfig: { textResponse: 'I see a person in the image.' },
      };

      const features = multimodalActionToActionFeatures(mockWorldState, action);

      expect(features.dense[0]).toBe(1); // respond_text
      expect(features.dense[1]).toBe(0); // not respond_voice
      expect(features.dense[5]).toBe(0); // no audio
      expect(features.sparse.actionType).toBe('respond_text');
    });

    it('should convert respond_multimodal action with audio', () => {
      const action: MultimodalAction = {
        type: 'respond_multimodal',
        description: 'Respond with text and audio',
        responseConfig: {
          textResponse: 'I see a person.',
          generateAudio: true,
          highlightVisualRegions: [{ bbox: [0.1, 0.2, 0.3, 0.4], label: 'person' }],
        },
      };

      const features = multimodalActionToActionFeatures(mockWorldState, action);

      expect(features.dense[2]).toBe(1); // respond_multimodal
      expect(features.dense[5]).toBe(1); // generateAudio
      expect(features.dense[6]).toBe(1); // highlightVisualRegions
      expect(features.sparse.requiresAudio).toBe(1);
      expect(features.sparse.requiresVisualHighlight).toBe(1);
    });

    it('should track input modalities in sparse features', () => {
      const action: MultimodalAction = {
        type: 'clarify',
        description: 'Ask for clarification',
      };

      const features = multimodalActionToActionFeatures(mockWorldState, action);

      expect(features.sparse.hasVisionInput).toBe(1);
      expect(features.sparse.hasVoiceInput).toBe(1);
      expect(features.sparse.hasTextInput).toBe(1);
    });
  });

  describe('multimodalHistoryToTrajectoryFeatures', () => {
    it('should convert turn history to trajectory features', () => {
      const history = {
        turns: [
          {
            timestamp: new Date(),
            role: 'user',
            modalities: { vision: true, voice: false, text: true },
          },
          {
            timestamp: new Date(),
            role: 'assistant',
            modalities: { vision: false, voice: true, text: true },
          },
          {
            timestamp: new Date(),
            role: 'user',
            modalities: { vision: true, voice: true, text: true },
          },
        ] as MultimodalTurn[],
      };

      const features = multimodalHistoryToTrajectoryFeatures(history);

      expect(features.dense[0]).toBe(3); // total turns
      expect(features.dense[1]).toBe(2); // vision turns
      expect(features.dense[2]).toBe(2); // voice turns
      expect(features.dense[3]).toBe(3); // text turns
    });

    it('should calculate modality rates', () => {
      const history = {
        turns: Array(10).fill(null).map((_, i) => ({
          timestamp: new Date(),
          role: i % 2 === 0 ? 'user' : 'assistant',
          modalities: {
            vision: i < 4,
            voice: i >= 3 && i < 7,
            text: true,
          },
        })) as MultimodalTurn[],
      };

      const features = multimodalHistoryToTrajectoryFeatures(history);

      expect(features.dense[4]).toBe(0.4); // 4/10 vision
      expect(features.dense[5]).toBe(0.4); // 4/10 voice
      expect(features.dense[6]).toBe(1.0); // 10/10 text
    });

    it('should count multimodal turns', () => {
      const history = {
        turns: [
          { timestamp: new Date(), role: 'user', modalities: { vision: true, voice: true, text: true } },
          { timestamp: new Date(), role: 'user', modalities: { vision: false, voice: false, text: true } },
          { timestamp: new Date(), role: 'user', modalities: { vision: true, voice: false, text: true } },
        ] as MultimodalTurn[],
      };

      const features = multimodalHistoryToTrajectoryFeatures(history);

      expect(features.sparse?.multimodalTurns).toBe(2); // First and third turns have 2+ modalities
    });
  });

  describe('multimodalMultiFocusToMultiFocusFeatures', () => {
    it('should convert visual object focus targets', () => {
      const targets: MultimodalFocusTarget[] = [
        {
          id: 'obj1',
          type: 'visual_object',
          visualRef: { objectLabel: 'person', bbox: [0.1, 0.2, 0.3, 0.4] },
          importance: 0.9,
          urgency: 0.7,
          recency: 0.95,
          lastMentioned: new Date(),
        },
      ];

      const features = multimodalMultiFocusToMultiFocusFeatures(targets);

      expect(features.targets).toHaveLength(1);
      expect(features.targets[0].dense[0]).toBe(0.9); // importance
      expect(features.targets[0].dense[1]).toBe(0.7); // urgency
      expect(features.targets[0].dense[2]).toBe(0.95); // recency
      expect(features.targets[0].dense[3]).toBe(1); // visual_object type
    });

    it('should convert speaker focus targets', () => {
      const targets: MultimodalFocusTarget[] = [
        {
          id: 'speaker1',
          type: 'speaker',
          speakerRef: { speakerId: 'user_123', isNewSpeaker: false, confidence: 0.85 },
          importance: 0.8,
          urgency: 0.6,
          recency: 1.0,
          lastMentioned: new Date(),
        },
      ];

      const features = multimodalMultiFocusToMultiFocusFeatures(targets);

      expect(features.targets[0].dense[4]).toBe(1); // speaker type
      expect(features.targets[0].sparse.speakerKnown).toBe(1);
    });

    it('should convert text concept focus targets', () => {
      const targets: MultimodalFocusTarget[] = [
        {
          id: 'concept1',
          type: 'text_concept',
          textRef: { concept: 'image', mentions: 3 },
          importance: 0.75,
          urgency: 0.5,
          recency: 0.8,
          lastMentioned: new Date(),
        },
      ];

      const features = multimodalMultiFocusToMultiFocusFeatures(targets);

      expect(features.targets[0].dense[5]).toBe(1); // text_concept type
      expect(features.targets[0].sparse.conceptMentions).toBe(3);
    });

    it('should handle mixed target types', () => {
      const targets: MultimodalFocusTarget[] = [
        { id: 'obj1', type: 'visual_object', importance: 0.9, urgency: 0.7, recency: 0.8, lastMentioned: new Date() },
        { id: 'spk1', type: 'speaker', importance: 0.8, urgency: 0.6, recency: 0.9, lastMentioned: new Date() },
        { id: 'cnc1', type: 'text_concept', importance: 0.7, urgency: 0.5, recency: 0.7, lastMentioned: new Date() },
        { id: 'pat1', type: 'cross_modal_pattern', importance: 0.85, urgency: 0.65, recency: 0.85, lastMentioned: new Date() },
      ];

      const features = multimodalMultiFocusToMultiFocusFeatures(targets);

      expect(features.targets).toHaveLength(4);
      expect(features.targets[0].dense[3]).toBe(1); // visual_object
      expect(features.targets[1].dense[4]).toBe(1); // speaker
      expect(features.targets[2].dense[5]).toBe(1); // text_concept
      expect(features.targets[3].dense[6]).toBe(1); // cross_modal_pattern
    });
  });
});
