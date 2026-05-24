// learning/monitoring.ts
// Minimal monitoring + rollback for organ versions

import { OrganType, OrganRegistry } from '../organs/registry';
import { getOrganConfig } from '../organs/organConfig';

interface OrganMetrics {
  version: string;
  mse: number;
  timestamp: Date;
}

function normalizeOrganTypeLabel(organType: string): OrganType | string {
  const normalized = organType.trim();
  if (normalized in OrganType) {
    return normalized as OrganType;
  }

  const lower = normalized.toLowerCase();
  if (lower === OrganType.PolicyPrior) return OrganType.PolicyPrior;
  if (lower === OrganType.RiskOutcome) return OrganType.RiskOutcome;
  if (lower === OrganType.Attention) return OrganType.Attention;

  if (normalized === 'PolicyPrior') return OrganType.PolicyPrior;
  if (normalized === 'RiskOutcome') return OrganType.RiskOutcome;
  if (normalized === 'Attention') return OrganType.Attention;

  return lower;
}

class OrganMonitor {
  private metrics: Map<string, OrganMetrics[]> = new Map();

  recordMetrics(domain: string, organType: string, version: string, mse: number): void {
    const canonicalOrganType = normalizeOrganTypeLabel(organType);
    const key = `${domain}:${canonicalOrganType}`;
    const entry = { version, mse, timestamp: new Date() };
    if (!this.metrics.has(key)) this.metrics.set(key, []);
    this.metrics.get(key)!.push(entry);
  }

  shouldRevert(domain: string, organType: string, currentMse: number): boolean {
    const canonicalOrganType = normalizeOrganTypeLabel(organType);
    const key = `${domain}:${canonicalOrganType}`;
    const config = getOrganConfig(domain, canonicalOrganType as OrganType);
    const threshold = config?.thresholds.maxMseIncrease || 0.1;

    const history = this.metrics.get(key) || [];
    if (history.length < 2) return false;
    
    const lastGood = history[history.length - 2];
    return (currentMse - lastGood.mse) > threshold;
  }

  getLastGoodVersion(domain: string, organType: string): string | undefined {
    const canonicalOrganType = normalizeOrganTypeLabel(organType);
    const key = `${domain}:${canonicalOrganType}`;
    const history = this.metrics.get(key) || [];
    return history.length > 1 ? history[history.length - 2].version : undefined;
  }

  rollbackOrgan(domain: string, organType: string): void {
    const canonicalOrganType = normalizeOrganTypeLabel(organType);
    const lastGood = this.getLastGoodVersion(domain, organType);
    if (lastGood) {
      console.log(`Rolling back ${domain} ${organType} to version ${lastGood}`);
      OrganRegistry.setCurrentVersion(canonicalOrganType as OrganType, domain, lastGood);
    }
  }
}

export const organMonitor = new OrganMonitor();
