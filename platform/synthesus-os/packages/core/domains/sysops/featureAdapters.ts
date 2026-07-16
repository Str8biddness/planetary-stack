// domains/sysops/featureAdapters.ts
// SysOps feature adapters mapping domain data to generic feature views for Synthesus 3.0

import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from '../../amplification/features';
import { SysWorldState, SysAction, SysHistory, SysFocusTarget } from './types';
import { toNumber } from '../../utils/normalization';

export function sysStateToStateFeatures(state: SysWorldState): StateFeatures {
  const dense: number[] = [
    state.hosts.reduce((sum, h) => sum + h.health, 0) / state.hosts.length,
    state.services.reduce((sum, s) => sum + s.health, 0) / state.services.length,
    state.incidents.filter(i => i.severity === 'critical').length,
    state.incidents.filter(i => i.severity === 'high').length,
    state.incidents.filter(i => i.severity === 'medium').length,
    state.incidents.length,
    state.alerts.length,
  ];
  const sparse: Record<string, number | string> = {
    avgHostErrorRate: state.hosts.reduce((sum, h) => sum + h.errorRate, 0) / state.hosts.length,
    avgServiceLatency: state.services.reduce((sum, s) => sum + s.latency, 0) / state.services.length,
    criticalIncidents: state.incidents.filter(i => i.severity === 'critical').length,
    unresolvedIncidents: state.incidents.filter(i => i.status !== 'resolved').length,
  };
  return { dense, sparse };
}

export function sysActionToActionFeatures(state: SysWorldState, action: SysAction): ActionFeatures {
  const dense: number[] = [
    action.type === 'runbook' ? 1 : 0,
    action.type === 'scale' ? 1 : 0,
    action.type === 'restart' ? 1 : 0,
    action.type === 'failover' ? 1 : 0,
    action.type === 'rollback' ? 1 : 0,
  ];
  const sparse: Record<string, number | string> = {
    actionType: action.type,
    targetHealth: state.hosts.find(h => h.id === action.target)?.health || state.services.find(s => s.name === action.target)?.health || 0.5,
    incidentCount: state.incidents.filter(i => i.services.includes(action.target)).length,
  };
  return { dense, sparse };
}

export function sysHistoryToTrajectoryFeatures(history: SysHistory): TrajectoryFeatures {
  const incidents = history.events.filter(e => e.type === 'incident');
  const actions = history.events.filter(e => e.type === 'action');
  const deploys = history.events.filter(e => e.type === 'deploy');
  const dense: number[] = [
    incidents.length,
    actions.length,
    deploys.length,
    incidents.filter(i => i.details.severity === 'critical').length,
    actions.filter(a => a.details.type === 'restart').length,
  ];
  const sparse: Record<string, number | string> = {
    incidentRate: incidents.length / Math.max(1, history.events.length),
    actionRate: actions.length / Math.max(1, history.events.length),
    deployRate: deploys.length / Math.max(1, history.events.length),
    stability: 1 - (incidents.length / Math.max(1, history.events.length)),
  };
  return { dense, sparse };
}

export function sysMultiFocusToMultiFocusFeatures(targets: SysFocusTarget[]): MultiFocusFeatures {
  const mappedTargets = targets.map(t => ({
    id: t.id,
    dense: [
      toNumber(t.severity),
      toNumber(t.recency),
      toNumber(t.connectivity),
    ],
    sparse: {
      type: t.type,
      severity: toNumber(t.severity),
      recency: toNumber(t.recency),
      connectivity: toNumber(t.connectivity),
    },
  }));
  return { targets: mappedTargets };
}
