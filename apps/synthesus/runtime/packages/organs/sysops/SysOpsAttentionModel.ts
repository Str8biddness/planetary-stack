// organs/sysops/SysOpsAttentionModel.ts
// Simple trainable model for SysOps Attention organ

import { MultiFocusFeatures } from '../../core/amplification/features';

export interface SysOpsAttentionModelParams {
  weights: number[][];
  bias: number[];
}

export class SysOpsAttentionModel {
  private params: SysOpsAttentionModelParams;

  constructor(params?: SysOpsAttentionModelParams) {
    this.params = params || {
      weights: Array(10).fill(Array(10).fill(0.1)),
      bias: Array(10).fill(0.0),
    };
  }

  toJSON(): SysOpsAttentionModelParams {
    return this.params;
  }

  static fromJSON(json: SysOpsAttentionModelParams): SysOpsAttentionModel {
    return new SysOpsAttentionModel(json);
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

  train(inputs: MultiFocusFeatures[], targets: number[][], options?: { epochs?: number; learningRate?: number }): void {
    const learningRate = options?.learningRate || 0.01;
    const epochs = options?.epochs || 10;

    for (let epoch = 0; epoch < epochs; epoch++) {
      let totalLoss = 0;
      for (let i = 0; i < inputs.length; i++) {
        const pred = this.score(inputs[i]);
        const target = targets[i];
        const loss = pred.reduce((sum, p, idx) => sum + (p - target[idx]) ** 2, 0) / pred.length;
        totalLoss += loss;

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
