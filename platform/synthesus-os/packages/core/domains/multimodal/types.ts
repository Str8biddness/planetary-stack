// domains/multimodal/types.ts
// Multimodal domain types for Synthesus 3.0
// Combines vision, voice, and text inputs into unified world state

export interface MultimodalWorldState {
  domain: 'multimodal';
  sessionId: string;
  timestamp: Date;

  // Individual modality states
  vision?: VisionState;
  voice?: VoiceState;
  text?: TextState;

  // Cross-modal alignment state
  alignment: AlignmentState;

  // Session context
  history: MultimodalTurn[];
  context: Record<string, any>;
}

export interface VisionState {
  imageUrl?: string;
  base64Data?: string;
  width: number;
  height: number;
  mimeType: string;
  timestamp: Date;

  // Processed features (populated by vision adapter)
  features?: {
    objects: Array<{
      label: string;
      confidence: number;
      bbox: [number, number, number, number];
    }>;
    scene: {
      primary: string;
      confidence: number;
      context: string[];
    };
    faces?: Array<{
      bbox: [number, number, number, number];
      emotion: string;
      confidence: number;
    }>;
    textContent?: string[];
  };
}

export interface VoiceState {
  audioUrl?: string;
  base64Data?: string;
  duration: number;
  sampleRate: number;
  channels: number;
  mimeType: string;
  timestamp: Date;
  language?: string;

  // Processed features (populated by voice adapter)
  transcript?: {
    text: string;
    confidence: number;
    isFinal: boolean;
  };
  acoustic?: {
    pitch: number;
    energy: number;
    speakingRate: number;
  };
  speaker?: {
    speakerId?: string;
    isNewSpeaker: boolean;
    confidence: number;
  };
  emotion?: {
    primary: string;
    confidence: number;
    intensity: number;
  };
}

export interface TextState {
  content: string;
  language: string;
  tokens: number;
  timestamp: Date;

  // Processing metadata
  embedding?: number[];
  intent?: string;
  sentiment?: 'positive' | 'negative' | 'neutral';
}

export interface AlignmentState {
  // Cross-modal alignment scores
  visionTextScore?: number;
  voiceTextScore?: number;
  visionVoiceScore?: number;

  // Unified representation
  fusedEmbedding?: number[];
  modalityWeights: {
    vision: number;
    voice: number;
    text: number;
  };

  // Overall confidence
  confidence: number;
}

export interface MultimodalTurn {
  timestamp: Date;
  role: 'user' | 'assistant';

  // What modalities were present in this turn
  modalities: {
    vision: boolean;
    voice: boolean;
    text: boolean;
  };

  // The actual content (only modalities that were present)
  vision?: VisionState;
  voice?: VoiceState;
  text?: TextState;

  // Assistant response (if role is assistant)
  response?: {
    text?: string;
    audioUrl?: string;
    emotion?: string;
  };
}

export interface MultimodalAction {
  type: 'respond_text' | 'respond_voice' | 'respond_multimodal' | 'clarify' | 'escalate';
  description: string;

  // Response configuration
  responseConfig?: {
    textResponse?: string;
    generateAudio?: boolean;
    emotion?: string;
    highlightVisualRegions?: Array<{
      bbox: [number, number, number, number];
      label: string;
    }>;
  };

  // Clarification request (if type is clarify)
  clarificationRequest?: {
    missingModalities: Array<'vision' | 'voice' | 'text'>;
    prompt: string;
  };

  parameters?: Record<string, any>;
}

export interface MultimodalFocusTarget {
  id: string;
  type: 'visual_object' | 'speaker' | 'text_concept' | 'cross_modal_pattern';

  // For visual objects
  visualRef?: {
    objectLabel: string;
    bbox?: [number, number, number, number];
  };

  // For speakers
  speakerRef?: {
    speakerId?: string;
    voiceprintConfidence?: number;
    isNewSpeaker?: boolean;
    confidence?: number;
  };

  // For text concepts
  textRef?: {
    concept: string;
    mentions: number;
  };

  // Attention weights
  importance: number; // 0-1
  urgency: number; // 0-1
  recency: number; // 0-1
  lastMentioned: Date;
}

export interface MultimodalInput {
  sessionId: string;
  query: CrossModalQuery;
  worldState: MultimodalWorldState;
}

export interface CrossModalQuery {
  text?: string;
  imageUrl?: string;
  audioUrl?: string;
  base64Image?: string;
  base64Audio?: string;
  language?: string;
  timestamp: Date;
}

export interface MultimodalOutput {
  action: MultimodalAction;
  updatedWorld: MultimodalWorldState;
  explanation: string;
}
