// learning/sysOpsTraceLogger.ts
// Teacher/Trace logging integration for SysOps domain in Synthesus 3.0

import { appendTraceEntry, TeacherTraceLogger, IntakeTraceEntry, PlanningTraceEntry, OutputTraceEntry } from './teacherTrace';

export class SysOpsTraceLoggerImpl implements TeacherTraceLogger {
  logIntake(entry: IntakeTraceEntry): void {
    appendTraceEntry({ ...entry, phase: 'intake', domain: 'sysops', organ: 'sysops_core' });
    console.log('[SysOps Intake]', entry);
  }

  logPlanning(entry: PlanningTraceEntry): void {
    appendTraceEntry({ ...entry, phase: 'planning', domain: 'sysops', organ: 'sysops_core' });
    console.log('[SysOps Planning]', entry);
  }

  logOutput(entry: OutputTraceEntry): void {
    appendTraceEntry({ ...entry, phase: 'output', domain: 'sysops', organ: 'sysops_core' });
    console.log('[SysOps Output]', entry);
  }
}

export async function logSysOpsIntake(sessionId: string, worldState: any, decision: any, outcome?: any): Promise<void> {
  const entry: IntakeTraceEntry = {
    sessionId,
    timestamp: new Date(),
    phase: 'intake',
    domain: 'sysops',
    organ: 'sysops_core',
    stateFeatures: {},
    organOutputs: {},
    decision,
    outcome,
  };
  new SysOpsTraceLoggerImpl().logIntake(entry);
}

export async function logSysOpsPlanning(sessionId: string, worldState: any, candidateActions: any[], chosenAction: any, organOutputs: any, decision: any, outcome?: any): Promise<void> {
  const entry: PlanningTraceEntry = {
    sessionId,
    timestamp: new Date(),
    phase: 'planning',
    domain: 'sysops',
    organ: 'sysops_core',
    stateFeatures: {},
    actionFeatures: [],
    chosenActionIndex: candidateActions.indexOf(chosenAction),
    organOutputs,
    decision,
    outcome,
  };
  new SysOpsTraceLoggerImpl().logPlanning(entry);
}

export async function logSysOpsOutput(sessionId: string, chosenAction: any, updatedWorld: any, organOutputs: any, decision: any, outcome?: any): Promise<void> {
  const entry: OutputTraceEntry = {
    sessionId,
    timestamp: new Date(),
    phase: 'output',
    domain: 'sysops',
    organ: 'sysops_core',
    stateFeatures: {},
    organOutputs,
    decision,
    outcome: {
      quality: 0.5,
      amplification: { fuelUsed: 10 },
      ...(outcome || {}),
    },
  };
  new SysOpsTraceLoggerImpl().logOutput(entry);
}
