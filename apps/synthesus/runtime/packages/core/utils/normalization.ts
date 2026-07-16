// utils/normalization.ts
// Safe numeric normalization helpers for Synthesus 3.0

export function toNumber(value: string | number | undefined | null): number {
  if (typeof value === 'number') return value;
  if (typeof value === 'string') {
    const parsed = parseFloat(value);
    if (!isNaN(parsed)) return parsed;
  }
  return 0; // fallback
}

export function clamp01(value: number): number {
  return Math.max(0, Math.min(1, value));
}
