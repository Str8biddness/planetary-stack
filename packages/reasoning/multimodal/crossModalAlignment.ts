// multimodal/crossModalAlignment.ts
// Cross-modal embedding alignment for Synthesus 3.0
// Fuses vision, voice, and text embeddings into unified multimodal representations

import { StateFeatures } from '../amplification/features';
import { VisionFeatures, MultimodalAlignment as VisionAlignment } from '../vision/visionAdapter';
import { VoiceFeatures, VoiceMultimodalAlignment } from '../voice/voiceSynthesis';

export interface TextEmbedding {
  text: string;
  embedding: number[];
  tokens: number;
  language: string;
}

export interface ModalityWeights {
  vision: number;
  voice: number;
  text: number;
}

export interface UnifiedMultimodalFeatures {
  // Individual modality features
  vision?: VisionFeatures;
  voice?: VoiceFeatures;
  text?: TextEmbedding;

  // Cross-modal alignments
  visionTextAlignment?: VisionAlignment;
  voiceTextAlignment?: VoiceMultimodalAlignment;
  visionVoiceAlignment?: number; // Cross-modal score between vision and voice

  // Unified representations
  fusedEmbedding: number[];
  modalityPresence: {
    hasVision: boolean;
    hasVoice: boolean;
    hasText: boolean;
  };
  modalityWeights: ModalityWeights;

  // Metadata
  timestamp: Date;
  fusionStrategy: 'weighted' | 'attention' | 'gate';
  confidence: number;
}

export interface CrossModalQuery {
  text?: string;
  imageUrl?: string;
  audioUrl?: string;
  base64Image?: string;
  base64Audio?: string;
  language?: string;
  sessionId: string;
  timestamp: Date;
}

export class CrossModalAligner {
  private embeddingDim: number = 128;
  private defaultWeights: ModalityWeights = {
    vision: 0.35,
    voice: 0.35,
    text: 0.30,
  };

  constructor() {}

  async processMultimodalQuery(query: CrossModalQuery): Promise<UnifiedMultimodalFeatures> {
    // Build initial modality presence from query
    const hasVisionInput = !!(query.imageUrl || query.base64Image);
    const hasVoiceInput = !!(query.audioUrl || query.base64Audio);
    const hasTextInput = !!query.text;

    const features: Partial<UnifiedMultimodalFeatures> = {
      modalityPresence: {
        hasVision: hasVisionInput,
        hasVoice: hasVoiceInput,
        hasText: hasTextInput,
      },
      modalityWeights: { ...this.defaultWeights },
      timestamp: new Date(),
      fusionStrategy: 'weighted',
      confidence: 0.0,
      fusedEmbedding: [],
    };

    // Process each modality if present
    if (hasTextInput && query.text) {
      features.text = await this.embedText(query.text, query.language || 'en');
    }

    if (hasVisionInput) {
      const { getVisionAdapter } = await import('../vision/visionAdapter');
      const visionAdapter = getVisionAdapter();
      const visionInput = {
        imageUrl: query.imageUrl,
        base64Data: query.base64Image,
        mimeType: query.base64Image ? 'image/jpeg' : 'image/jpeg',
        width: 0,
        height: 0,
        timestamp: new Date(),
        source: 'upload' as const,
      };
      features.vision = await visionAdapter.processImage(visionInput);

      if (features.text) {
        features.visionTextAlignment = await visionAdapter.alignWithText(
          features.vision,
          query.text
        );
      }
    }

    if (hasVoiceInput) {
      const { getVoiceSynthesis } = await import('../voice/voiceSynthesis');
      const voiceSynth = getVoiceSynthesis();
      const voiceInput = {
        audioUrl: query.audioUrl,
        base64Data: query.base64Audio,
        mimeType: query.base64Audio ? 'audio/wav' : 'audio/wav',
        duration: 0,
        sampleRate: 16000,
        channels: 1,
        timestamp: new Date(),
        source: 'upload' as const,
        language: query.language,
      };
      features.voice = await voiceSynth.extractFeatures(voiceInput);

      if (features.text) {
        features.voiceTextAlignment = await voiceSynth.alignWithText(
          features.voice,
          query.text
        );
      }
    }

    // Compute vision-voice alignment if both present
    const hasVision = features.vision !== undefined;
    const hasVoice = features.voice !== undefined;
    const hasText = features.text !== undefined;

    if (hasVision && hasVoice && features.vision && features.voice) {
      features.visionVoiceAlignment = this.computeVisionVoiceAlignment(
        features.vision,
        features.voice
      );
    }

    // Build modality presence for weight computation with guaranteed values
    const modalityPresence: { hasVision: boolean; hasVoice: boolean; hasText: boolean } = {
      hasVision: features.vision !== undefined,
      hasVoice: features.voice !== undefined,
      hasText: features.text !== undefined,
    };
    features.modalityPresence = modalityPresence;

    // Adaptive weight adjustment based on alignment scores
    features.modalityWeights = this.computeAdaptiveWeights(features);

    // Fuse embeddings
    features.fusedEmbedding = this.fuseMultimodalEmbeddings(features);

    // Compute overall confidence
    features.confidence = this.computeOverallConfidence(features);

    return features as UnifiedMultimodalFeatures;
  }

  toStateFeatures(unified: UnifiedMultimodalFeatures): StateFeatures {
    const dense = [
      unified.modalityPresence.hasVision ? 1 : 0,
      unified.modalityPresence.hasVoice ? 1 : 0,
      unified.modalityPresence.hasText ? 1 : 0,
      unified.modalityWeights.vision,
      unified.modalityWeights.voice,
      unified.modalityWeights.text,
      unified.confidence,
      unified.visionTextAlignment?.crossModalScore ?? 0.5,
      unified.voiceTextAlignment?.crossModalScore ?? 0.5,
      unified.visionVoiceAlignment ?? 0.5,
    ];

    const sparse: Record<string, number | string> = {
      hasVision: unified.modalityPresence.hasVision ? 1 : 0,
      hasVoice: unified.modalityPresence.hasVoice ? 1 : 0,
      hasText: unified.modalityPresence.hasText ? 1 : 0,
      fusionStrategy: unified.fusionStrategy,
      confidence: unified.confidence,
      alignmentScore: (
        (unified.visionTextAlignment?.crossModalScore ?? 0.5) +
        (unified.voiceTextAlignment?.crossModalScore ?? 0.5) +
        (unified.visionVoiceAlignment ?? 0.5)
      ) / 3,
    };

    return { dense, sparse };
  }

  private async embedText(text: string, language: string): Promise<TextEmbedding> {
    // Placeholder: In production, this would call the text embedding model
    const embedding = Array.from({ length: this.embeddingDim }, () => 0);
    for (let i = 0; i < text.length; i++) {
      embedding[i % this.embeddingDim] += text.charCodeAt(i) / 1000;
    }
    const norm = Math.sqrt(embedding.reduce((a, b) => a + b * b, 0));
    const normalized = embedding.map(x => x / (norm + 1e-8));

    return {
      text,
      embedding: normalized,
      tokens: text.split(/\s+/).length,
      language,
    };
  }

  private computeVisionVoiceAlignment(vision: VisionFeatures, voice: VoiceFeatures): number {
    // Compute cross-modal alignment between vision and voice embeddings
    const dot = vision.embedding.reduce((a, b, i) => a + b * voice.embedding[i], 0);
    const normV = Math.sqrt(vision.embedding.reduce((a, b) => a + b * b, 0));
    const normVo = Math.sqrt(voice.embedding.reduce((a, b) => a + b * b, 0));
    return 0.5 + 0.5 * (dot / (normV * normVo + 1e-8));
  }

  private computeAdaptiveWeights(
    features: Partial<UnifiedMultimodalFeatures>
  ): ModalityWeights {
    const presence = features.modalityPresence!;
    let weights = { ...this.defaultWeights };

    // Adjust weights based on alignment scores
    if (presence.hasVision && presence.hasText && features.visionTextAlignment) {
      const alignment = features.visionTextAlignment.crossModalScore;
      // If vision-text alignment is poor, reduce vision weight
      weights.vision *= (0.5 + alignment);
    }

    if (presence.hasVoice && presence.hasText && features.voiceTextAlignment) {
      const alignment = features.voiceTextAlignment.crossModalScore;
      // If voice-text alignment is poor, reduce voice weight
      weights.voice *= (0.5 + alignment);
    }

    // Normalize to sum to 1
    const sum = weights.vision + weights.voice + weights.text;
    weights.vision /= sum;
    weights.voice /= sum;
    weights.text /= sum;

    // If a modality is absent, redistribute its weight
    if (!presence.hasVision) {
      const vWeight = weights.vision;
      weights.vision = 0;
      weights.voice += vWeight * 0.5;
      weights.text += vWeight * 0.5;
    }
    if (!presence.hasVoice) {
      const voWeight = weights.voice;
      weights.voice = 0;
      weights.vision += voWeight * 0.5;
      weights.text += voWeight * 0.5;
    }
    if (!presence.hasText) {
      const tWeight = weights.text;
      weights.text = 0;
      weights.vision += tWeight * 0.5;
      weights.voice += tWeight * 0.5;
    }

    return weights;
  }

  private fuseMultimodalEmbeddings(features: Partial<UnifiedMultimodalFeatures>): number[] {
    const fused = Array.from({ length: this.embeddingDim }, () => 0);
    const weights = features.modalityWeights!;

    if (features.vision) {
      const aligned = features.visionTextAlignment?.alignedEmbedding || features.vision.embedding;
      for (let i = 0; i < this.embeddingDim; i++) {
        fused[i] += weights.vision * aligned[i];
      }
    }

    if (features.voice) {
      const aligned = features.voiceTextAlignment?.alignedEmbedding || features.voice.embedding;
      for (let i = 0; i < this.embeddingDim; i++) {
        fused[i] += weights.voice * aligned[i];
      }
    }

    if (features.text) {
      for (let i = 0; i < this.embeddingDim; i++) {
        fused[i] += weights.text * features.text.embedding[i];
      }
    }

    return fused;
  }

  private computeOverallConfidence(features: Partial<UnifiedMultimodalFeatures>): number {
    const presence = features.modalityPresence!;
    const modalityCount = (presence.hasVision ? 1 : 0) + (presence.hasVoice ? 1 : 0) + (presence.hasText ? 1 : 0);

    // Base confidence from modality presence
    let confidence = modalityCount / 3;

    // Adjust by alignment scores
    let alignmentSum = 0;
    let alignmentCount = 0;

    if (features.visionTextAlignment) {
      alignmentSum += features.visionTextAlignment.crossModalScore;
      alignmentCount++;
    }
    if (features.voiceTextAlignment) {
      alignmentSum += features.voiceTextAlignment.crossModalScore;
      alignmentCount++;
    }
    if (features.visionVoiceAlignment) {
      alignmentSum += features.visionVoiceAlignment;
      alignmentCount++;
    }

    if (alignmentCount > 0) {
      const avgAlignment = alignmentSum / alignmentCount;
      confidence = 0.6 * confidence + 0.4 * avgAlignment;
    }

    return Math.min(1.0, Math.max(0.0, confidence));
  }
}

// Singleton instance
let _crossModalAligner: CrossModalAligner | null = null;

export function getCrossModalAligner(): CrossModalAligner {
  if (!_crossModalAligner) {
    _crossModalAligner = new CrossModalAligner();
  }
  return _crossModalAligner;
}

export function resetCrossModalAligner(): void {
  _crossModalAligner = null;
}
