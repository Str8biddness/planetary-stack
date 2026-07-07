// organs/chat/ChatPolicyPriorModel.ts
// Simple trainable model for Chat PolicyPrior organ

import { StateFeatures, ActionFeatures } from '../../core/amplification/features';
import { ChatPolicyPriorInput, ChatPolicyPriorTarget } from '../../core/learning/chat/policyPriorData';

export interface ChatPolicyPriorModelParams {
  weights: number[];
  bias: number;
}

export class ChatPolicyPriorModel {
  private params: ChatPolicyPriorModelParams;

  constructor(params?: ChatPolicyPriorModelParams) {
    this.params = params || {
      weights: Array(10).fill(0.1),
      bias: 0.0,
    };
  }

  toJSON(): ChatPolicyPriorModelParams {
    return this.params;
  }

  static fromJSON(json: ChatPolicyPriorModelParams): ChatPolicyPriorModel {
    return new ChatPolicyPriorModel(json);
  }

  /**
   * Score each candidate action given the current state.
   * Returns one raw logit per action.
   */
  score(state: StateFeatures, actions: ActionFeatures[]): number[] {
    return actions.map(action => {
      let logit = this.params.bias;
      if (action.dense) {
        for (let j = 0; j < action.dense.length && j < this.params.weights.length; j++) {
          logit += action.dense[j] * this.params.weights[j];
        }
      }
      return logit;
    });
  }

  /**
   * Train using quality-weighted cross-entropy style loss.
   * Nudges scores so the chosen action gets a relatively higher score,
   * weighted by quality.
   */
  train(
    inputs: ChatPolicyPriorInput[],
    targets: ChatPolicyPriorTarget[],
    options?: { epochs?: number; learningRate?: number }
  ): void {
    const epochs = options?.epochs ?? 10;
    const lr = options?.learningRate ?? 0.01;

    for (let epoch = 0; epoch < epochs; epoch++) {
      let totalLoss = 0;

      for (let i = 0; i < inputs.length; i++) {
        const { stateFeatures, actionFeaturesList } = inputs[i];
        const { chosenIndex, quality } = targets[i];
        const logits = this.score(stateFeatures, actionFeaturesList);

        // Softmax
        const maxLogit = Math.max(...logits);
        const exps = logits.map(l => Math.exp(l - maxLogit));
        const sumExp = exps.reduce((s, e) => s + e, 0);
        const probs = exps.map(e => e / sumExp);

        // Cross-entropy loss for the chosen action, weighted by quality
        const chosenProb = Math.max(probs[chosenIndex] ?? probs[0], 1e-8);
        totalLoss += -quality * Math.log(chosenProb);

        // Gradient: for softmax + cross-entropy, grad_j = quality * (prob_j - 1{j==chosen})
        const grad = probs.map((p, j) => quality * (p - (j === chosenIndex ? 1 : 0)));

        // Update bias
        this.params.bias -= lr * grad.reduce((s, g) => s + g, 0);

        // Update weights using action features
        for (let j = 0; j < Math.min(this.params.weights.length, actionFeaturesList.length); j++) {
          const dense = actionFeaturesList[j]?.dense;
          if (!dense) continue;
          for (let k = 0; k < Math.min(dense.length, this.params.weights.length); k++) {
            this.params.weights[k] -= lr * grad[j] * dense[k];
          }
        }
      }

      console.log(`Epoch ${epoch}: Loss ${totalLoss / Math.max(inputs.length, 1)}`);
    }
  }
}
