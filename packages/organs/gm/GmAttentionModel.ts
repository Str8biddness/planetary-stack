// organs/gm/GmAttentionModel.ts
// Simple trainable model for GM Attention organ

import { MultiFocusFeatures } from '../../amplification/features';

export interface GmAttentionModelParams {
  weights: number[][];
  bias: number[];
}

export class GmAttentionModel {
  private params: GmAttentionModelParams;

  constructor(params?: GmAttentionModelParams) {
    this.params = params || {
      weights: Array(10).fill(Array(10).fill(0.1)),
      bias: Array(10).fill(0.0),
    };
  }

  toJSON(): GmAttentionModelParams {
    return this.params;
  }

  static fromJSON(json: GmAttentionModelParams): GmAttentionModel {
    return new GmAttentionModel(json);
  }

  score(input: MultiFocusFeatures): number[] {
    const logits = this.params.bias.slice();
    for (let i = 0; i < input.targets.length; i++) {
      const target = input.targets[i];
      if (target.dense) {
        for (let j = 0; j < target.dense.length && j < this.params.weights[i]?.length; j++) {
          logits[i] += target.dense[j] * this.params.weights[i][j];
        }
      }
    }
    const expLogits = logits.map(Math.exp);
    const sum = expLogits.reduce((s, v) => s + v, 0);
    return expLogits.map(v => v / sum);
  }

  train(inputs: MultiFocusFeatures[], targets: number[][]): void {
    const learningRate = 0.01;
    const epochs = 10;

    for (let epoch = 0; epoch < epochs; epoch++) {
      let totalLoss = 0;
      for (let i = 0; i < inputs.length; i++) {
        const pred = this.score(inputs[i]);
        const target = targets[i];
        const loss = pred.reduce((sum, p, idx) => sum + (p - target[idx]) ** 2, 0) / pred.length;
        totalLoss += loss;

        // Stub GD for softmax
        for (let j = 0; j < pred.length; j++) {
          const grad = pred[j] - target[j];
          this.params.bias[j] -= learningRate * grad;
          if (inputs[i].targets[j]?.dense) {
            for (let k = 0; k < inputs[i].targets[j].dense!.length && k < this.params.weights[j].length; k++) {
              this.params.weights[j][k] -= learningRate * grad * inputs[i].targets[j].dense![k];
            }
          }
        }
      }
      console.log(`Epoch ${epoch}: Loss ${totalLoss / inputs.length}`);
    }
  }
}
