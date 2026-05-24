// amplification/index.ts
// Amplification Plane entrypoints and types for Synthesus 3.0

import { CloudParameterManager, CloudParameters } from '../utils/cloudParameters';
import { registerDefaultOrgans } from '../organs/bootstrap';

registerDefaultOrgans();

export interface AmplificationContext {
  computeBudget: number;
  sessionId: string;
  domain: string;
  allowedOrgans?: string[];
  cloudParams: CloudParameters;  // Required: Cloud parameters for all operations
}

export interface IntakeAmplificationResult {
  summaries: any[];
  anomalyFlags: any[];
}

export interface PlanningAmplificationResult {
  rankedActions: Array<{ action: any; score: number; trajectory?: any; riskScore?: any }>;
  topTrajectories: Array<{ trajectory: any; riskScore: number }>;
  references: any[];
}

import { ExecutionRecommendation } from '../utils/guardrails';

export interface OutputAmplificationResult {
  sanityCheckPassed: boolean;
  operatorExplanation: string;
  internalSummary: string;
  executionRecommendation: ExecutionRecommendation;
}

import { ChatWorldState, ChatAction } from '../domains/chat/types';
import { SysWorldState, SysAction } from '../domains/sysops/types';
import { GMWorldState, GMAction } from '../domains/gm/types';
import { MultimodalWorldState, MultimodalAction } from '../domains/multimodal/types';

import {
  amplifyIntake as chatAmplifyIntake,
  amplifyPlanning as chatAmplifyPlanning,
  amplifyOutput as chatAmplifyOutput,
} from './chatAmplification';

import {
  amplifyIntake as sysopsAmplifyIntake,
  amplifyPlanning as sysopsAmplifyPlanning,
  amplifyOutput as sysopsAmplifyOutput,
} from './sysopsAmplification';

import {
  amplifyIntake as gmAmplifyIntake,
  amplifyPlanning as gmAmplifyPlanning,
  amplifyOutput as gmAmplifyOutput,
} from './gmAmplification';

import {
  amplifyIntake as multimodalAmplifyIntake,
  amplifyPlanning as multimodalAmplifyPlanning,
  amplifyOutput as multimodalAmplifyOutput,
} from './multimodalAmplification';

function isChatWorldState(ws: any): ws is ChatWorldState {
  return ws && ws.domain === 'chat';
}
function isSysWorldState(ws: any): ws is SysWorldState {
  return ws && ws.domain === 'sysops';
}
function isGMWorldState(ws: any): ws is GMWorldState {
  return ws && ws.domain === 'gm';
}
function isMultimodalWorldState(ws: any): ws is MultimodalWorldState {
  return ws && ws.domain === 'multimodal';
}

export async function amplifyIntake(ctx: AmplificationContext, input: any): Promise<IntakeAmplificationResult> {
  const ws = input?.worldState;
  if (isChatWorldState(ws)) {
    return chatAmplifyIntake(ctx, input as { worldState: ChatWorldState; rawInput: any });
  }
  if (isSysWorldState(ws)) {
    return sysopsAmplifyIntake(ctx, input as { worldState: SysWorldState; rawInput: any });
  }
  if (isGMWorldState(ws)) {
    return gmAmplifyIntake(ctx, input as { worldState: GMWorldState; rawInput: any });
  }
  if (isMultimodalWorldState(ws)) {
    return multimodalAmplifyIntake(ctx, input as { worldState: MultimodalWorldState; rawInput: any });
  }
  return { summaries: [], anomalyFlags: [] };
}

export async function amplifyPlanning(ctx: AmplificationContext, input: any): Promise<PlanningAmplificationResult> {
  const ws = input?.worldState;
  const actions = input?.candidateActions || [];
  if (isChatWorldState(ws)) {
    return chatAmplifyPlanning(ctx, { worldState: ws, candidateActions: actions as ChatAction[] });
  }
  if (isSysWorldState(ws)) {
    return sysopsAmplifyPlanning(ctx, { worldState: ws, candidateActions: actions as SysAction[] });
  }
  if (isGMWorldState(ws)) {
    return gmAmplifyPlanning(ctx, { worldState: ws, candidateActions: actions as GMAction[] });
  }
  if (isMultimodalWorldState(ws)) {
    return multimodalAmplifyPlanning(ctx, { worldState: ws, candidateActions: actions as MultimodalAction[] });
  }
  return { rankedActions: [], topTrajectories: [], references: [] };
}

export async function amplifyOutput(ctx: AmplificationContext, input: any): Promise<OutputAmplificationResult> {
  const ws = input?.updatedWorld;
  const action = input?.chosenAction;
  if (isChatWorldState(ws) && action) {
    return chatAmplifyOutput(ctx, { chosenAction: action as ChatAction, updatedWorld: ws });
  }
  if (isSysWorldState(ws) && action) {
    return sysopsAmplifyOutput(ctx, { chosenAction: action as SysAction, updatedWorld: ws });
  }
  if (isGMWorldState(ws) && action) {
    return gmAmplifyOutput(ctx, { chosenAction: action as GMAction, updatedWorld: ws });
  }
  if (isMultimodalWorldState(ws) && action) {
    return multimodalAmplifyOutput(ctx, { chosenAction: action as MultimodalAction, updatedWorld: ws });
  }
  return {
    sanityCheckPassed: true,
    operatorExplanation: 'No domain match; proceeding with defaults',
    internalSummary: 'amplifyOutput fallback executed',
    executionRecommendation: ExecutionRecommendation.REQUEST_CONFIRMATION,
  };
}
