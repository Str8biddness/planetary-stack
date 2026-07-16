// frontend/src/api/amplificationClient.ts
// API client for Amplification Plane and monitoring endpoints

import type { HealthResponse } from '../types';

const API_BASE = '';

export interface AmplificationStatus {
  enabled: boolean;
  available: boolean;
  domains_supported: string[];
  intake_calls: number;
  planning_calls: number;
  output_calls: number;
  fallback_count: number;
  last_error: string | null;
}

export interface AmplificationMetrics {
  triad_scores: {
    avg_risk: number;
    avg_confidence: number;
    avg_attention: number;
  };
  organ_usage: {
    policy_prior: number;
    risk_outcome: number;
    attention: number;
    anomaly_event: number;
    summarizer: number;
  };
  execution_recommendations: {
    PROCEED: number;
    REQUEST_CONFIRMATION: number;
    HALT: number;
  };
  domain_breakdown: Record<string, { calls: number; avg_latency_ms: number }>;
  timestamp: string;
}

export interface DashboardData {
  system: {
    status: string;
    version: string;
    uptime_seconds: number;
    uptime_human: string;
    timestamp: string;
  };
  components: {
    ml_swarm: { enabled: boolean; status: string; models_loaded: number };
    rag: { enabled: boolean; status: string; vectors: number };
    amplification_plane: { enabled: boolean; status: string; domains: string[] };
    cognitive_engines: { active: number; characters_with_engines: string[] };
    synthesus_master: { enabled: boolean; status: string };
    veai_trainer: { enabled: boolean; status: string };
    parameter_cloud_v2: { 
      enabled: boolean; 
      status: string; 
      total_parameters: number; 
      hemispheres: string[]; 
      shard_count: number 
    };
  };
  traffic: {
    total_requests: number;
    active_sessions: number;
    characters_loaded: number;
    requests_per_minute: number;
  };
  cognitive_state?: {
    t: number;
    current_domain: string;
    belief_count: number;
    hypothesis_count: number;
    registry_size: number;
  };
  recent_logs?: Array<{
    timestamp: string;
    level: string;
    message: string;
    component: string;
  }>;
  alerts: Array<{ level: string; component: string; message: string }>;
}

export interface MultimodalQueryRequest {
  query: string;
  character_id: string;
  session_id?: string;
  base64Image?: string;
  imageMimeType?: string;
  base64Audio?: string;
  audioMimeType?: string;
  imageUrl?: string;
  audioUrl?: string;
}

export interface MultimodalQueryResponse {
  response: string;
  confidence: number;
  character: string;
  session_id: string;
  latency_ms: number;
  amplification_info?: {
    risk_score: number;
    confidence_margin: number;
    attention_sensitivity: number;
    execution_recommendation: string;
    organ_scores: Record<string, number>;
  };
  sources?: Array<Record<string, unknown>>;
  emotion?: string;
}

class AmplificationAPIClient {
  private async fetch<T>(endpoint: string, options?: RequestInit): Promise<T> {
    const response = await fetch(`${API_BASE}${endpoint}`, {
      headers: { 'Content-Type': 'application/json' },
      ...options,
    });

    if (!response.ok) {
      throw new Error(`API error: ${response.status} ${response.statusText}`);
    }

    return response.json();
  }

  // Health and status
  async getHealth(): Promise<HealthResponse> {
    return this.fetch<HealthResponse>('/api/v1/health');
  }

  async getDashboard(): Promise<DashboardData> {
    return this.fetch<DashboardData>('/api/v1/monitoring/dashboard');
  }

  // Amplification endpoints
  async getAmplificationStatus(): Promise<AmplificationStatus> {
    return this.fetch<AmplificationStatus>('/api/v1/amplification/status');
  }

  async getAmplificationMetrics(): Promise<AmplificationMetrics> {
    return this.fetch<AmplificationMetrics>('/api/v1/amplification/metrics');
  }

  // Multimodal query
  async sendMultimodalQuery(request: MultimodalQueryRequest): Promise<MultimodalQueryResponse> {
    return this.fetch<MultimodalQueryResponse>('/api/v1/query', {
      method: 'POST',
      body: JSON.stringify(request),
    });
  }

  // Characters
  async getCharacters(): Promise<{ characters: CharacterInfo[]; count: number }> {
    return this.fetch('/api/v1/characters');
  }

  async getCharacter(charId: string): Promise<CharacterInfo> {
    return this.fetch(`/api/v1/characters/${charId}`);
  }

  // Admin and Simulation
  async getAdminKeys(adminKey: string): Promise<any[]> {
    return this.fetch('/api/v1/admin/api-keys', {
      headers: { 'X-API-Key': adminKey }
    });
  }

  async createAdminKey(adminKey: string, label: string): Promise<any> {
    return this.fetch('/api/v1/admin/api-keys', {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-API-Key': adminKey 
      },
      body: JSON.stringify({ label })
    });
  }

  async getAdminUsage(adminKey: string): Promise<any> {
    return this.fetch('/api/v1/admin/usage', {
      headers: { 'X-API-Key': adminKey }
    });
  }

  async getConsciousState(adminKey: string, charId: string = 'synth'): Promise<any> {
    return this.fetch(`/api/v1/conscious_state?character_id=${charId}`, {
      headers: { 'X-API-Key': adminKey }
    });
  }

  async evolveCharacter(adminKey: string, charId: string): Promise<any> {
    return this.fetch(`/api/v1/admin/evolve/${charId}`, {
      method: 'POST',
      headers: { 
        'Content-Type': 'application/json',
        'X-API-Key': adminKey 
      }
    });
  }
}

export interface CharacterInfo {
  id: string;
  name: string;
  role: string;
  description: string;
  domains: string[];
  personality_traits: string[];
  ethics_disclosure: string;
}

export const amplificationClient = new AmplificationAPIClient();
export default amplificationClient;
