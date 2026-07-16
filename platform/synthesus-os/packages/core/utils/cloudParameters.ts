// utils/cloudParameters.ts
// Cloud parameter manager for Synthesus 3.0

import * as fs from 'fs';
import { dirname, resolve as path_resolve } from 'path';
import { fileURLToPath } from 'url';

// Support both CJS (__dirname) and ESM (import.meta.url) contexts
const CURRENT_DIR: string = typeof __dirname !== 'undefined'
  ? __dirname
  : dirname(fileURLToPath((globalThis as any).import_meta_url || 'file:///'));

export interface CloudParameterConfig {
  cloud_endpoint: string;
  api_key: string;
  cache_duration_ms: number;
  update_interval_ms: number;
  local_fallback_enabled: boolean;
}

export interface CloudParameters {
  temperature?: number;
  top_k?: number;
  top_p?: number;
  max_tokens?: number;
  repetition_penalty?: number;
  compute_budget_multiplier?: number;
  attention_weights?: Record<string, number>;
  organ_priorities?: Record<string, number>;
  risk_thresholds?: Record<string, number>;
  domain_weights?: Record<string, number>;
  latency_targets?: Record<string, number>;
  current_load_factor?: number;
  performance_metrics?: Record<string, number>;
  adaptation_rates?: Record<string, number>;
}

const LOCAL_DEFAULTS: CloudParameters = {
  temperature: 1.0,
  top_k: 50,
  top_p: 1.0,
  max_tokens: 128,
  repetition_penalty: 1.1,
  compute_budget_multiplier: 1.0,
  attention_weights: { policy: 0.3, risk: 0.3, attention: 0.4 },
  organ_priorities: { PolicyPrior: 1, RiskOutcome: 1, Attention: 1, AnomalyEvent: 0.8, Summarizer: 0.9 },
  risk_thresholds: { max_risk: 0.7, min_confidence: 0.6 },
  domain_weights: { chat: 1.0, gm: 1.0, sysops: 1.0 },
  latency_targets: { intake: 50, planning: 200, output: 100 },
  current_load_factor: 1.0,
  performance_metrics: { accuracy: 0.85, latency: 150, throughput: 10 },
  adaptation_rates: { learning_rate: 0.001, momentum: 0.9 },
};

export interface PerformanceMetrics {
  fetch_latency: number;
  update_latency: number;
  cache_hit_rate: number;
  error_rate: number;
  last_successful_fetch: number;
}

export class CloudParameterManager {
  private cachedParams: CloudParameters | null = null;
  private lastFetchTime: number = 0;
  private updateTimer: ReturnType<typeof setInterval> | null = null;
  private performanceMetrics: PerformanceMetrics = {
    fetch_latency: 0,
    update_latency: 0,
    cache_hit_rate: 1.0,
    error_rate: 0,
    last_successful_fetch: 0,
  };
  private connectionPool: any[] = [];
  private prefetchBuffer: CloudParameters | null = null;

  constructor(private config: CloudParameterConfig) {
    this.initializeConnectionPool();
    if (this.isCloudEnabled()) {
      this.startContinuousUpdates();
    }
  }

  async getParameters(): Promise<CloudParameters> {
    const now = Date.now();

    if (!this.isCloudEnabled()) {
      this.cachedParams = this.cachedParams || { ...LOCAL_DEFAULTS };
      this.lastFetchTime = now;
      return this.cachedParams;
    }

    if (this.cachedParams && (now - this.lastFetchTime) < this.config.cache_duration_ms) {
      this.performanceMetrics.cache_hit_rate = Math.min(1.0, this.performanceMetrics.cache_hit_rate + 0.01);
      return this.cachedParams;
    }

    this.performanceMetrics.cache_hit_rate = Math.max(0.0, this.performanceMetrics.cache_hit_rate - 0.05);

    if (this.prefetchBuffer && (now - this.lastFetchTime) < this.config.cache_duration_ms * 2) {
      this.cachedParams = this.prefetchBuffer;
      this.prefetchBuffer = null;
      this.lastFetchTime = now;
      return this.cachedParams;
    }

    try {
      const startTime = performance.now();
      const params = await this.fetchFromCloud();
      const fetchTime = performance.now() - startTime;

      this.performanceMetrics.fetch_latency = fetchTime;
      this.performanceMetrics.last_successful_fetch = now;
      this.performanceMetrics.error_rate = Math.max(0.0, this.performanceMetrics.error_rate - 0.1);

      this.cachedParams = { ...LOCAL_DEFAULTS, ...params };
      this.lastFetchTime = now;
      this.prefetchParameters();
      return this.cachedParams;
    } catch (error) {
      this.performanceMetrics.error_rate = Math.min(1.0, this.performanceMetrics.error_rate + 0.1);

      if (this.config.local_fallback_enabled && this.cachedParams) {
        console.warn('Failed to fetch cloud parameters, using cached parameters:', error);
        return this.cachedParams;
      }
      if (this.config.local_fallback_enabled) {
        console.warn('Failed to fetch cloud parameters, using local defaults:', error);
        this.cachedParams = { ...LOCAL_DEFAULTS };
        this.lastFetchTime = now;
        return this.cachedParams;
      }
      throw new Error(`Cloud parameter fetch failed and no fallback available: ${error}`);
    }
  }

  async updateParameters(updates: Partial<CloudParameters>): Promise<void> {
    if (!this.isCloudEnabled()) {
      throw new Error('Cloud endpoint and API key required for parameter updates');
    }

    const startTime = performance.now();

    try {
      await this.pushUpdatesToCloud(updates);
      const updateTime = performance.now() - startTime;
      this.performanceMetrics.update_latency = updateTime;
      this.cachedParams = null;
      this.lastFetchTime = 0;
    } catch (error) {
      this.performanceMetrics.error_rate = Math.min(1.0, this.performanceMetrics.error_rate + 0.1);
      throw new Error(`Failed to update cloud parameters: ${error}`);
    }
  }

  getPerformanceMetrics(): PerformanceMetrics & { total_parameters?: number } {
    const stats_path = path_resolve(CURRENT_DIR, '..', 'data', 'parameter_cloud_v2_stats.json');
    let total_params = 41346;
    try {
      if (fs.existsSync(stats_path)) {
        const stats = JSON.parse(fs.readFileSync(stats_path, 'utf8'));
        total_params = stats.total_parameters;
      }
    } catch {
      // Fallback
    }

    return { ...this.performanceMetrics, total_parameters: total_params };
  }

  private isCloudEnabled(): boolean {
    return Boolean(
      this.config.cloud_endpoint &&
      this.config.api_key &&
      this.config.update_interval_ms > 0
    );
  }

  private async fetchFromCloud(): Promise<Partial<CloudParameters>> {
    const connection = this.getConnectionFromPool();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 5000);

    try {
      const response = await fetch(`${this.config.cloud_endpoint}/fetch`, {
        method: 'GET',
        headers: {
          'Authorization': `Bearer ${this.config.api_key}`,
          'Content-Type': 'application/json',
          'X-Client-Version': 'synthesus-3.0',
        },
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Cloud parameter fetch failed: ${response.statusText}`);
      }

      const data = await response.json();
      this.returnConnectionToPool(connection);
      if (!data || typeof data !== 'object') {
        throw new Error('Cloud parameter fetch returned invalid JSON');
      }
      const params = (data as any).parameters;
      if (!params || typeof params !== 'object') {
        throw new Error('Cloud parameter fetch response missing parameters');
      }
      return params as Partial<CloudParameters>;
    } catch (error) {
      clearTimeout(timeoutId);
      this.returnConnectionToPool(connection);
      throw error;
    }
  }

  private async pushUpdatesToCloud(updates: Partial<CloudParameters>): Promise<void> {
    const connection = this.getConnectionFromPool();
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 3000);

    try {
      const response = await fetch(`${this.config.cloud_endpoint}/update`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.config.api_key}`,
          'Content-Type': 'application/json',
          'X-Client-Version': 'synthesus-3.0',
        },
        body: JSON.stringify({
          updates,
          timestamp: Date.now(),
          performance_metrics: this.performanceMetrics,
        }),
        signal: controller.signal,
      });

      clearTimeout(timeoutId);

      if (!response.ok) {
        throw new Error(`Cloud parameter update failed: ${response.statusText}`);
      }

      this.returnConnectionToPool(connection);
    } catch (error) {
      clearTimeout(timeoutId);
      this.returnConnectionToPool(connection);
      throw error;
    }
  }

  private startContinuousUpdates(): void {
    if (!this.isCloudEnabled()) {
      return;
    }
    this.updateTimer = setInterval(async () => {
      try {
        await this.pushPerformanceMetrics();
      } catch (error) {
        console.warn('Failed to push performance metrics:', error);
      }
    }, this.config.update_interval_ms);
  }

  private async pushPerformanceMetrics(): Promise<void> {
    if (!this.isCloudEnabled()) return;

    const connection = this.getConnectionFromPool();

    try {
      await fetch(`${this.config.cloud_endpoint}/metrics`, {
        method: 'POST',
        headers: {
          'Authorization': `Bearer ${this.config.api_key}`,
          'Content-Type': 'application/json',
        },
        body: JSON.stringify({
          metrics: this.performanceMetrics,
          timestamp: Date.now(),
        }),
      });
    } catch {
      // Silent failure for metrics
    } finally {
      this.returnConnectionToPool(connection);
    }
  }

  private async prefetchParameters(): Promise<void> {
    if (!this.prefetchBuffer) {
      try {
        this.prefetchBuffer = await this.fetchFromCloud();
      } catch {
        // Silent prefetch failure
      }
    }
  }

  private initializeConnectionPool(): void {
    for (let i = 0; i < 3; i++) {
      this.connectionPool.push({ id: i, inUse: false });
    }
  }

  private getConnectionFromPool(): any {
    const available = this.connectionPool.find(conn => !conn.inUse);
    if (available) {
      available.inUse = true;
      return available;
    }
    const newConn = { id: this.connectionPool.length, inUse: false };
    this.connectionPool.push(newConn);
    newConn.inUse = true;
    return newConn;
  }

  private returnConnectionToPool(connection: any): void {
    connection.inUse = false;
  }

  destroy(): void {
    if (this.updateTimer) {
      clearInterval(this.updateTimer);
      this.updateTimer = null;
    }
    this.connectionPool = [];
  }
}
