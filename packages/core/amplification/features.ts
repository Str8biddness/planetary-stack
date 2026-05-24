// amplification/features.ts
// Domain-agnostic feature views for Synthesus 3.0

export interface StateFeatures {
  dense?: number[]; // Vector of numeric features
  sparse?: Record<string, number | string>; // Key-value features
}

export interface ActionFeatures {
  dense?: number[];
  sparse?: Record<string, number | string>;
}

export interface TrajectoryFeatures {
  dense?: number[]; // Summary of trajectory (e.g., avg state, length)
  sparse?: Record<string, number | string>; // E.g., unresolvedConflicts, coherence
}

export interface MultiFocusFeatures {
  targets: Array<{
    id: string;
    dense?: number[];
    sparse?: Record<string, number | string>;
  }>;
}
