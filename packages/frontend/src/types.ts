// Synthesus 3.0 — Shared TypeScript Types

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: string;
  confidence?: number;
  source?: string;
  emotion?: string;
  character?: string;
  error?: boolean;
  latency_ms?: number;
  debug?: Record<string, any>;
  // Amplification info
  amplificationInfo?: {
    riskScore: number;
    confidenceMargin: number;
    attentionSensitivity: number;
    executionRecommendation: string;
    organScores: Record<string, number>;
  };
}

export interface QueryRequest {
  query: string;
  character: string;
  mode: string;
  session_id?: string;
  player_id?: string;
  include_sources?: boolean;
  include_debug?: boolean;
  // Multimodal support
  base64Image?: string;
  imageMimeType?: string;
  base64Audio?: string;
  audioMimeType?: string;
  imageUrl?: string;
  audioUrl?: string;
}

export interface QueryResponse {
  response: string;
  confidence: number;
  character: string;
  source: string;
  session_id: string;
  latency_ms: number;
  sources?: Array<Record<string, unknown>>;
  emotion?: string;
  relationship?: Record<string, unknown>;
  debug?: Record<string, unknown>;
  // Amplification info
  amplification_info?: {
    risk_score: number;
    confidence_margin: number;
    attention_sensitivity: number;
    execution_recommendation: string;
    organ_scores: Record<string, number>;
  };
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

export interface HealthResponse {
  status: string;
  version: string;
  uptime_seconds: number;
  ml_swarm: {
    enabled: boolean;
    models: number;
    footprint_kb: number;
  };
  rag: {
    enabled: boolean;
    vectors: number;
  };
  characters_loaded: number;
  cognitive_engines_active: number;
  active_sessions: number;
  total_requests: number;
  timestamp: string;
  // Amplification status
  amplification?: {
    enabled: boolean;
    available: boolean;
    domains_supported: string[];
  };
}

// Amplification types
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

// Dashboard types
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
  };
  traffic: {
    total_requests: number;
    active_sessions: number;
    characters_loaded: number;
    requests_per_minute: number;
  };
  alerts: Array<{ level: string; component: string; message: string }>;
}
