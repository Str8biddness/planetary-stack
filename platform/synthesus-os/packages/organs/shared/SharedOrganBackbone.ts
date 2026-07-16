import { ActionFeatures, MultiFocusFeatures, StateFeatures, TrajectoryFeatures } from '../../core/amplification/features';
import { clamp01, toNumber } from '../../core/utils/normalization';

export interface SharedOrganFeatures {
  latentVector: number[];
  latentStrength: number;
  signals: string[];
  summary: string;
}

export class SharedOrganBackbone {
  private readonly kind: string;
  private readonly width: number;

  constructor(kind: string, width = 12) {
    this.kind = kind;
    this.width = width;
  }

  encodeState(features: StateFeatures): SharedOrganFeatures {
    const vector = this.normalizeVector([
      this.read(features.sparse, 'criticalIncidents'),
      this.read(features.sparse, 'unresolvedIncidents'),
      this.read(features.sparse, 'unresolvedQuestions'),
      this.read(features.sparse, 'confusion'),
      this.read(features.sparse, 'frustration'),
      this.read(features.sparse, 'safety'),
      this.read(features.sparse, 'clarity'),
      this.read(features.sparse, 'stability'),
      this.read(features.sparse, 'resolution'),
      this.read(features.sparse, 'topicCount') / 10,
      this.read(features.sparse, 'avgServiceLatency') / 500,
      this.read(features.sparse, 'avgHostErrorRate'),
    ]);
    return this.package('state', vector, this.stateSignals(features));
  }

  encodeTrajectory(features: TrajectoryFeatures): SharedOrganFeatures {
    const vector = this.normalizeVector([
      this.read(features.sparse, 'confusionRate'),
      this.read(features.sparse, 'safetyRate'),
      this.read(features.sparse, 'resolution'),
      this.read(features.sparse, 'turnBalance'),
      this.read(features.sparse, 'incidentRate'),
      this.read(features.sparse, 'actionRate'),
      this.read(features.sparse, 'deployRate'),
      this.read(features.sparse, 'stability'),
      this.read(features.sparse, 'spawnRate'),
      this.read(features.sparse, 'combatRate'),
      this.read(features.sparse, 'npcTickRate'),
      this.read(features.sparse, 'coherence'),
    ]);
    return this.package('trajectory', vector, this.trajectorySignals(features));
  }

  encodeAction(state: StateFeatures, action: ActionFeatures): SharedOrganFeatures {
    const stateLatent = this.encodeState(state);
    const actionVector = this.normalizeVector([
      this.read(action.sparse, 'importance'),
      this.read(action.sparse, 'urgency'),
      this.read(action.sparse, 'severity'),
      this.read(action.sparse, 'recency'),
      this.read(action.sparse, 'connectivity'),
      this.read(action.sparse, 'risk'),
      this.read(action.sparse, 'reward'),
      ...(action.dense ?? []).slice(0, 5),
    ]);
    const mixed = this.mixVectors(stateLatent.latentVector, actionVector);
    return this.package('action', mixed, stateLatent.signals);
  }

  encodeMultiFocus(features: MultiFocusFeatures): SharedOrganFeatures {
    const vector = this.normalizeVector(
      features.targets.flatMap(target => [
        this.read(target.sparse, 'importance'),
        this.read(target.sparse, 'urgency'),
        this.read(target.sparse, 'severity'),
        this.read(target.sparse, 'recency'),
        this.read(target.sparse, 'connectivity'),
        ...(target.dense ?? []).slice(0, 2),
      ])
    );
    const signals = features.targets.map(target => target.id).slice(0, 4);
    return this.package('multifocus', vector, signals);
  }

  private package(scope: string, latentVector: number[], signals: string[]): SharedOrganFeatures {
    const latentStrength = clamp01(latentVector.reduce((sum, value) => sum + Math.abs(value), 0) / Math.max(1, latentVector.length));
    return {
      latentVector,
      latentStrength,
      signals: Array.from(new Set(signals)).slice(0, 8),
      summary: `${this.kind}:${scope} latent=${latentStrength.toFixed(2)}`,
    };
  }

  private normalizeVector(values: number[]): number[] {
    const vector = values.slice(0, this.width).map(value => clamp01(Number.isFinite(value) ? value : 0));
    while (vector.length < this.width) vector.push(0);
    return vector;
  }

  private mixVectors(a: number[], b: number[]): number[] {
    const width = Math.max(a.length, b.length, this.width);
    const mixed: number[] = [];
    for (let i = 0; i < width; i++) {
      mixed.push(clamp01(((a[i] ?? 0) * 0.6) + ((b[i] ?? 0) * 0.4)));
    }
    return mixed.slice(0, this.width);
  }

  private read(block: Record<string, number | string> | undefined, key: string): number {
    if (!block) return 0;
    return toNumber(block[key] as number | string | undefined);
  }

  private stateSignals(features: StateFeatures): string[] {
    const signals: string[] = [];
    if (this.read(features.sparse, 'criticalIncidents') > 0) signals.push('critical_incidents');
    if (this.read(features.sparse, 'unresolvedQuestions') > 0) signals.push('unresolved_questions');
    if (this.read(features.sparse, 'confusion') > 0.3) signals.push('confusion');
    if (this.read(features.sparse, 'frustration') > 0.3) signals.push('frustration');
    if (this.read(features.sparse, 'avgServiceLatency') > 0) signals.push('latency');
    return signals;
  }

  private trajectorySignals(features: TrajectoryFeatures): string[] {
    const signals: string[] = [];
    if (this.read(features.sparse, 'confusionRate') > 0.3) signals.push('confusion_rate');
    if (this.read(features.sparse, 'incidentRate') > 0.2) signals.push('incident_rate');
    if (this.read(features.sparse, 'stability') > 0.6) signals.push('stability');
    if (this.read(features.sparse, 'resolution') > 0.5) signals.push('resolution');
    return signals;
  }
}
