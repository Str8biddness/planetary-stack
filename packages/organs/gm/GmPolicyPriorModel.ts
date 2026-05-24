// organs/gm/GmPolicyPriorModel.ts
// Simple trainable model for GM PolicyPrior organ

import { StateFeatures, ActionFeatures } from '../../amplification/features';

export interface GmPolicyPriorModelParams {
  weights: number[];
  bias: number;
}

export class GmPolicyPriorModel {
  private params: GmPolicyPriorModelParams;

  constructor(params?: GmPolicyPriorModelParams) {
    this.params = params || {
      weights: Array(10).fill(0.1),
      bias: 0.0,
    };
  }

  toJSON(): GmPolicyPriorModelParams {
    return this.params;
  }

  static fromJSON(json: GmPolicyPriorModelParams): GmPolicyPriorModel {
    return new GmPolicyPriorModel(json);
  }

  score(input: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }): number[] {
    return input.actionFeaturesList.map(action => {
      let logit = this.params.bias;
      if (action.dense) {
        for (let j = 0; j < action.dense.length && j < this.params.weights.length; j++) {
          logit += action.dense[j] * this.params.weights[j];
        }
      }
      return logit;
    });
  }

  train(inputs: { stateFeatures: StateFeatures; actionFeaturesList: ActionFeatures[] }[], targets: number[][]): void {
    const learningRate = 0.01;
    const epochs = 10;

    for (let epoch = 0; epoch < epochs; epoch++) {
      let totalLoss = 0;
      for (let i = 0; i < inputs.length; i++) {
        const pred = this.score(inputs[i]);
        const target = targets[i];
        const loss = pred.reduce((sum, p, idx) => sum + (p - target[idx]) ** 2, 0) / pred.length;
        totalLoss += loss;

        // Stub GD
        const grad = pred.map((p, idx) => 2 * (p - target[idx]) / pred.length);
        this.params.bias -= learningRate * grad.reduce((s, g) => s + g, 0);
        for (let j = 0; j < Math.min(5, this.params.weights.length); j++) {
          const dW = grad.reduce((s, g, idx) => s + g * (inputs[i].actionFeaturesList[idx]?.dense?.[j] || 0), 0);
          this.params.weights[j] -= learningRate * dW;
        }
      }
      console.log(`Epoch ${epoch}: Loss ${totalLoss / inputs.length}`);
    }
  }
}
