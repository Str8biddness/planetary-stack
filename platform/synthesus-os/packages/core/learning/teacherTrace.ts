// learning/teacherTrace.ts
// Teacher/Trace logging interfaces for Synthesus 3.0

import * as fs from 'fs';
import path from 'path';
import { StateFeatures, ActionFeatures, TrajectoryFeatures, MultiFocusFeatures } from '../amplification/features';

export type TracePhase = 'intake' | 'planning' | 'output';

export interface TraceReplayMetadata {
  generator: string;
  seed: number;
  scenarioId: string;
  step: number;
  simulatedTime: string;
  record?: Record<string, any>;
  chal?: {
    frameId: string;
    parentFrameId: string;
    device: string;
    role: 'organ_accelerator';
    route: string;
    outputRef: string;
    candidateRefs?: string[];
    selectedCandidateRef?: string;
    criticFeedback?: Record<string, any>;
  };
}

export interface IntakeTraceEntry {
  sessionId: string;
  timestamp: Date;
  phase?: TracePhase;
  domain?: string;
  organ?: string;
  stateFeatures?: StateFeatures;
  organOutputs?: Record<string, any>;
  decision?: any;
  outcome?: any;
  replay?: TraceReplayMetadata;
}

export interface PlanningTraceEntry {
  sessionId: string;
  timestamp: Date;
  phase?: TracePhase;
  domain?: string;
  organ?: string;
  stateFeatures?: StateFeatures;
  actionFeatures?: ActionFeatures[];
  chosenActionIndex?: number;
  multiFocusFeatures?: MultiFocusFeatures;
  organOutputs?: Record<string, any>;
  decision?: any;
  outcome?: {
    quality?: number;
    [key: string]: any;
  };
  trajectoryFeatures?: TrajectoryFeatures;
  replay?: TraceReplayMetadata;
}

export interface OutputTraceEntry {
  sessionId: string;
  timestamp: Date;
  phase?: TracePhase;
  domain?: string;
  organ?: string;
  stateFeatures?: StateFeatures;
  actionFeatures?: ActionFeatures[];
  organOutputs?: Record<string, any>;
  decision?: any;
  outcome?: {
    quality?: number;
    amplification?: {
      fuelUsed?: number;
    };
    [key: string]: any;
  };
  trajectoryFeatures?: TrajectoryFeatures;
  multiFocusFeatures?: MultiFocusFeatures;
  attentionWeights?: number[];
  chosenActionIndex?: number;
  replay?: TraceReplayMetadata;
}

export interface TeacherTraceLogger {
  logIntake(entry: IntakeTraceEntry): void;
  logPlanning(entry: PlanningTraceEntry): void;
  logOutput(entry: OutputTraceEntry): void;
}

const TRACE_FILE = path.resolve(__dirname, '../../../logs/teacher_traces.jsonl');

function ensureTraceDirectory(): void {
  fs.mkdirSync(path.dirname(TRACE_FILE), { recursive: true });
}

function serializeEntry(entry: IntakeTraceEntry | PlanningTraceEntry | OutputTraceEntry): string {
  return JSON.stringify(entry);
}

function parseEntry(line: string): any | null {
  const trimmed = line.trim();
  if (!trimmed) return null;
  try {
    const parsed = JSON.parse(trimmed);
    if (parsed?.timestamp) {
      parsed.timestamp = new Date(parsed.timestamp);
    }
    return parsed;
  } catch {
    return null;
  }
}

export function appendTraceEntry(entry: IntakeTraceEntry | PlanningTraceEntry | OutputTraceEntry): void {
  ensureTraceDirectory();
  fs.appendFileSync(TRACE_FILE, `${serializeEntry(entry)}\n`, 'utf8');
}

export async function loadEntries(
  options: { domain?: string; from?: Date; to?: Date; phase?: TracePhase }
): Promise<any[]> {
  if (!fs.existsSync(TRACE_FILE)) {
    return [];
  }

  const fromMs = options.from?.getTime();
  const toMs = options.to?.getTime();
  const lines = fs.readFileSync(TRACE_FILE, 'utf8').split(/\r?\n/);
  const entries = lines
    .map(parseEntry)
    .filter((entry): entry is Record<string, any> => Boolean(entry))
    .filter(entry => !options.domain || entry.domain === options.domain)
    .filter(entry => !options.phase || entry.phase === options.phase)
    .filter(entry => {
      const ts = new Date(entry.timestamp).getTime();
      if (Number.isNaN(ts)) return false;
      if (fromMs !== undefined && ts < fromMs) return false;
      if (toMs !== undefined && ts > toMs) return false;
      return true;
    });

  return entries;
}
