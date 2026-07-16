// domains/sysops/types.ts
// SysOps domain types for Synthesus 3.0

export interface SysHost {
  id: string;
  health: number; // 0-1
  errorRate: number;
  latency: number;
  saturation: number;
  lastRestart?: Date;
}

export interface SysService {
  name: string;
  health: number;
  dependencies: string[];
  errorRate: number;
  latency: number;
  lastDeploy?: Date;
}

export interface SysIncident {
  id: string;
  severity: 'low' | 'medium' | 'high' | 'critical';
  startTime: Date;
  duration?: number;
  services: string[];
  blastRadius: number; // 0-1
  status: 'open' | 'mitigating' | 'resolved';
}

export interface SysWorldState {
  domain: string;
  hosts: SysHost[];
  services: SysService[];
  incidents: SysIncident[];
  alerts: string[];
  timestamp: Date;
}

export interface SysAction {
  type: 'runbook' | 'scale' | 'restart' | 'failover' | 'rollback' | 'ticket_update';
  target: string; // host or service ID
  parameters?: Record<string, any>;
  description: string;
}

export interface SysHistory {
  events: Array<{
    timestamp: Date;
    type: 'incident' | 'action' | 'deploy' | 'config_change';
    details: any;
  }>;
}

export interface SysFocusTarget {
  id: string;
  type: 'host' | 'service' | 'incident' | 'cluster';
  severity?: number;
  recency?: number; // 0-1
  connectivity?: number; // 0-1
}
