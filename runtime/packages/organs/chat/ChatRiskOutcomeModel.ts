// organs/chat/ChatRiskOutcomeModel.ts
// Simple trainable model for Chat RiskOutcome organ

import { TrajectoryFeatures } from '../../core/amplification/features';

export interface ChatRiskOutcomeModelParams {
  weights: number[];
  bias: number;
}

export class ChatRiskOutcomeModel {
  private params: ChatRiskOutcomeModelParams;

  constructor(params?: ChatRiskOutcomeModelParams) {
    this.params = params || {
      weights: Array(10).fill(0.1),
      bias: 0.0,
    };
  }

  toJSON(): ChatRiskOutcomeModelParams {
    return this.params;
  }

  static fromJSON(json: ChatRiskOutcomeModelParams): ChatRiskOutcomeModel {
    return new ChatRiskOutcomeModel(json);
  }

  score(trajectoryFeatures: TrajectoryFeatures): number {
    let logit = this.params.bias;
    if (trajectoryFeatures.dense) {
      for (let j = 0; j < trajectoryFeatures.dense.length && j < this.params.weights.length; j++) {
        logit += trajectoryFeatures.dense[j] * this.params.weights[j];
      }
    }
    return Math.tanh(logit);
  }

  train(inputs: TrajectoryFeatures[], targets: number[], options?: { epochs?: number; learningRate?: number }): void {
    const learningRate = options?.learningRate || 0.01;
    const epochs = options?.epochs || 10;

    for (let epoch = 0; epoch < epochs; epoch++) {
      let totalLoss = 0;
      for (let i = 0; i < inputs.length; i++) {
        const pred = this.score(inputs[i]);
        const target = targets[i];
        const loss = (pred - target) ** 2;
        totalLoss += loss;

        // Stub GD
        const grad = 2 * (pred - target) * (1 - pred ** 2);
        this.params.bias -= learningRate * grad;
        for (let j = 0; j < Math.min(5, this.params.weights.length); j++) {
          const dW = grad * (inputs[i].dense?.[j] || 0);
          this.params.weights[j] -= learningRate * grad * (inputs[i].dense?.[j] || 0);
        }
      }
      console.log(`Epoch ${epoch}: Loss ${totalLoss / inputs.length}`);
    }
  }
}
