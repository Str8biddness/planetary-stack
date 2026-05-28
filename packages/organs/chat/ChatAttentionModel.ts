// organs/chat/ChatAttentionModel.ts
// Simple trainable model for Chat Attention organ

import { MultiFocusFeatures } from '../../core/amplification/features';

// Linear model: weights per target, optional bias
export interface ChatAttentionModelParams {
  weights: number[]; // One per focus target (assume max 10 for now)
  bias: number;
}

export class ChatAttentionModel {
  private params: ChatAttentionModelParams;

  constructor(params?: ChatAttentionModelParams) {
    this.params = params || {
      weights: Array(10).fill(0.1),
      bias: 0.0,
    };
  }

  toJSON(): ChatAttentionModelParams {
    return this.params;
  }

  static fromJSON(json: ChatAttentionModelParams): ChatAttentionModel {
    return new ChatAttentionModel(json);
  }

  // Score: compute logits, then softmax
  score(multiFocusFeatures: MultiFocusFeatures): number[] {
    const n = Math.min(multiFocusFeatures.targets.length, this.params.weights.length);
    const logits: number[] = [];
    for (let i = 0; i < n; i++) {
      // Simple linear combination of target features
      const target = multiFocusFeatures.targets[i];
      let logit = this.params.bias;
      if (target.dense) {
        for (let j = 0; j < target.dense.length && j < this.params.weights.length; j++) {
          logit += target.dense[j] * this.params.weights[j];
        }
      } else {
        logit += this.params.weights[i] || 0.1;
      }
      logits.push(logit);
    }
    // Softmax
    const maxLogit = Math.max(...logits);
    const exp = logits.map(l => Math.exp(l - maxLogit));
    const sumExp = exp.reduce((s, e) => s + e, 0);
    return exp.map(e => e / sumExp);
  }

  // Training: simple gradient descent on MSE between predicted and target weight vectors
  train(inputs: MultiFocusFeatures[], targets: number[][], options?: { epochs?: number; learningRate?: number }): void {
    const learningRate = options?.learningRate || 0.01;
    const epochs = options?.epochs || 10;

    for (let epoch = 0; epoch < epochs; epoch++) {
      let totalLoss = 0;
      for (let i = 0; i < inputs.length; i++) {
        const pred = this.score(inputs[i]);
        const target = targets[i];
        // MSE loss
        const loss = pred.reduce((sum, p, idx) => sum + (p - target[idx]) ** 2, 0) / pred.length;
        totalLoss += loss;

        // Stub GD: update bias and first few weights (simplified)
        this.params.bias -= learningRate * (pred[0] - target[0]) * 0.1; // tiny step
        for (let j = 0; j < Math.min(5, this.params.weights.length); j++) {
          const grad = (pred[0] - target[0]) * (inputs[i].targets[0]?.dense?.[j] || 0);
          this.params.weights[j] -= learningRate * grad;
        }
      }
      console.log(`Epoch ${epoch}: Loss ${totalLoss / inputs.length}`);
    }
  }
}
