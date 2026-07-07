// utils/cloudParametersV2.ts
// Scalable parameter manager for billions of parameters
// Supports batching, sharding, and selective fetching

export type ParameterValueType = 'float' | 'vector' | 'sparse' | 'json';

export interface ParameterValue {
  value: any;
  value_type: ParameterValueType;
  metadata?: Record<string, any>;
  version: number;
  updated_at_ms: number;
}

export interface BatchFetchRequest {
  namespace_patterns: string[];  // e.g., ["model.layers.*", "organ.chat.*"]
  include_metadata?: boolean;
  max_results?: number;
  cursor?: string | null;
}

export interface BatchFetchResponse {
  parameters: Record<string, ParameterValue>;
  count: number;
  cursor: string | null;
  version: number;
}

export interface BatchUpdateRequest {
  updates: Record<string, {
    value: any;
    value_type: ParameterValueType;
    metadata?: Record<string, any>;
  }>;
  strategy?: 'merge' | 'replace' | 'gradient';
  learning_rate?: number;
}

export interface ParameterQuery {
  namespace_prefix?: string;
  tags?: string[];
  min_importance?: number;
  updated_after_ms?: number;
  limit?: number;
  cursor?: string | null;
}

export interface ShardedParameterConfig {
  cloud_endpoint: string;
  api_key: string;
  // Shard-aware configuration
  preferred_shards?: string[];  // e.g., ["model.layers", "organ.chat"]
  local_cache_max_mb: number;   // Max local cache size
  batch_fetch_size: number;     // Default: 10000
  prefetch_patterns?: string[]; // Patterns to prefetch in background
  compression_enabled: boolean;
  // Performance tuning
  connection_pool_size: number;
  fetch_timeout_ms: number;
  retry_attempts: number;
}

interface CacheEntry {
  value: ParameterValue;
  last_accessed_ms: number;
  access_count: number;
  size_bytes: number;
}

interface ShardRouting {
  shard_key: string;
  host: string;
  port: number;
  healthy: boolean;
  latency_ms: number;
}

export class ScalableParameterManager {
  private config: ShardedParameterConfig;
  private cache: Map<string, CacheEntry> = new Map();
  private cache_size_bytes: number = 0;
  private max_cache_bytes: number;
  private shard_routing: Map<string, ShardRouting> = new Map();
  private connection_pool: Array<{ busy: boolean; last_used: number }> = [];
  private metrics = {
    fetch_count: 0,
    cache_hit_count: 0,
    batch_fetch_count: 0,
    update_count: 0,
    total_bytes_fetched: 0,
    total_latency_ms: 0
  };

  constructor(config: ShardedParameterConfig) {
    this.config = {
      ...config,
      batch_fetch_size: config.batch_fetch_size || 10000,
      compression_enabled: config.compression_enabled !== undefined ? config.compression_enabled : true,
      connection_pool_size: config.connection_pool_size || 10,
      fetch_timeout_ms: config.fetch_timeout_ms || 30000,
      retry_attempts: config.retry_attempts || 3,
    };
    this.max_cache_bytes = (config.local_cache_max_mb || 100) * 1024 * 1024;
    this._init_connection_pool();
    this._start_background_tasks();
  }

  // ==================== PUBLIC API ====================

  /**
   * Fetch parameters matching namespace patterns
   * Efficient for billions of params - only fetches matching patterns
   */
  async fetchBatch(request: BatchFetchRequest): Promise<BatchFetchResponse> {
    const start_time = Date.now();
    
    const response = await this._fetch_from_cloud('/fetch-batch', {
      namespace_patterns: request.namespace_patterns,
      include_metadata: request.include_metadata ?? true,
      max_results: request.max_results ?? this.config.batch_fetch_size,
      cursor: request.cursor
    });

    // Update cache with fetched parameters
    for (const [key, value] of Object.entries(response.parameters)) {
      this._set_cache(key, value as ParameterValue);
    }

    this.metrics.batch_fetch_count++;
    this.metrics.total_bytes_fetched += JSON.stringify(response).length;
    this.metrics.total_latency_ms += Date.now() - start_time;

    return response as BatchFetchResponse;
  }

  /**
   * Get a single parameter - checks cache first, then fetches
   */
  async getParameter(namespace: string): Promise<ParameterValue | null> {
    // Check cache first
    const cached = this._get_cache(namespace);
    if (cached) {
      this.metrics.cache_hit_count++;
      return cached;
    }

    // Fetch specific parameter
    const response = await this.fetchBatch({
      namespace_patterns: [namespace],
      max_results: 1
    });

    return response.parameters[namespace] || null;
  }

  /**
   * Batch update parameters
   * Supports merge, replace, and gradient strategies
   */
  async updateBatch(request: BatchUpdateRequest): Promise<{ updated: number; version: number }> {
    const response = await this._fetch_from_cloud('/update-batch', {
      updates: request.updates,
      strategy: request.strategy || 'merge',
      learning_rate: request.learning_rate
    });

    // Update cache with new values
    for (const [key, update] of Object.entries(request.updates)) {
      const cached = this._get_cache(key);
      if (cached) {
        // Merge with cached value
        const merged: ParameterValue = {
          value: request.strategy === 'replace' 
            ? update.value 
            : this._merge_values(cached.value, update.value),
          value_type: update.value_type,
          metadata: { ...cached.metadata, ...update.metadata },
          version: cached.version + 1,
          updated_at_ms: Date.now()
        };
        this._set_cache(key, merged);
      }
    }

    this.metrics.update_count += Object.keys(request.updates).length;
    return response as { updated: number; version: number };
  }

  /**
   * Query parameters with advanced filtering
   */
  async query(query: ParameterQuery): Promise<{ results: Array<{ namespace: string; key: string; value: any }>; count: number }> {
    const response = await this._fetch_from_cloud('/query', {
      namespace_prefix: query.namespace_prefix,
      tags: query.tags,
      min_importance: query.min_importance,
      updated_after_ms: query.updated_after_ms,
      limit: query.limit || 1000,
      cursor: query.cursor
    });

    return response as { results: Array<{ namespace: string; key: string; value: any }>; count: number };
  }

  /**
   * Stream all parameters matching pattern (for large datasets)
   * Yields parameters in batches
   */
  async *streamParameters(pattern: string, batch_size: number = 1000): AsyncGenerator<{ namespace: string; value: ParameterValue }> {
    let cursor: string | null = null;
    let has_more = true;

    while (has_more) {
      const response = await this.fetchBatch({
        namespace_patterns: [pattern],
        max_results: batch_size,
        cursor
      });

      for (const [namespace, value] of Object.entries(response.parameters)) {
        yield { namespace, value: value as ParameterValue };
      }

      cursor = response.cursor;
      has_more = cursor !== null;
    }
  }

  /**
   * Prefetch parameters in background
   * Useful for loading model weights before inference
   */
  async prefetch(patterns: string[]): Promise<void> {
    // Non-blocking prefetch
    this.fetchBatch({
      namespace_patterns: patterns,
      max_results: this.config.batch_fetch_size
    }).catch(err => {
      console.warn('Prefetch failed:', err);
    });
  }

  /**
   * Get cache statistics
   */
  getCacheStats(): {
    size_entries: number;
    size_bytes: number;
    max_bytes: number;
    hit_rate: number;
    utilization_percent: number;
  } {
    const hit_rate = this.metrics.fetch_count > 0
      ? this.metrics.cache_hit_count / (this.metrics.cache_hit_count + this.metrics.fetch_count)
      : 0;

    return {
      size_entries: this.cache.size,
      size_bytes: this.cache_size_bytes,
      max_bytes: this.max_cache_bytes,
      hit_rate,
      utilization_percent: (this.cache_size_bytes / this.max_cache_bytes) * 100
    };
  }

  /**
   * Get performance metrics
   */
  getPerformanceMetrics(): {
    fetch_count: number;
    batch_fetch_count: number;
    cache_hit_count: number;
    update_count: number;
    avg_fetch_latency_ms: number;
    total_bytes_fetched: number;
  } {
    return {
      ...this.metrics,
      avg_fetch_latency_ms: this.metrics.batch_fetch_count > 0
        ? this.metrics.total_latency_ms / this.metrics.batch_fetch_count
        : 0
    };
  }

  /**
   * Clear local cache
   */
  clearCache(): void {
    this.cache.clear();
    this.cache_size_bytes = 0;
  }

  /**
   * Dispose and cleanup
   */
  destroy(): void {
    this.clearCache();
    this.connection_pool = [];
  }

  // ==================== PRIVATE METHODS ====================

  private _init_connection_pool(): void {
    for (let i = 0; i < this.config.connection_pool_size; i++) {
      this.connection_pool.push({ busy: false, last_used: 0 });
    }
  }

  private _start_background_tasks(): void {
    // Periodic cache eviction
    setInterval(() => this._evict_cache(), 60000);
    
    // Health check for shards
    setInterval(() => this._health_check_shards(), 30000);
  }

  private async _fetch_from_cloud(endpoint: string, body: any, retry_count: number = 0): Promise<any> {
    const url = `${this.config.cloud_endpoint}${endpoint}`;
    
    try {
      const controller = new AbortController();
      const timeout = setTimeout(() => controller.abort(), this.config.fetch_timeout_ms);

      const response = await fetch(url, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this.config.api_key}`,
          'X-Client-Version': '2.0'
        },
        body: JSON.stringify(body),
        signal: controller.signal
      });

      clearTimeout(timeout);

      if (!response.ok) {
        const error = await response.text();
        throw new Error(`HTTP ${response.status}: ${error}`);
      }

      const data = await response.json();
      
      // Decompress if needed
      if (this.config.compression_enabled && data.compressed) {
        return this._decompress(data);
      }
      
      return data;
    } catch (error) {
      if (retry_count < this.config.retry_attempts) {
        // Exponential backoff
        const delay = Math.pow(2, retry_count) * 100;
        await new Promise(resolve => setTimeout(resolve, delay));
        return this._fetch_from_cloud(endpoint, body, retry_count + 1);
      }
      throw error;
    }
  }

  private _get_cache(namespace: string): ParameterValue | null {
    const entry = this.cache.get(namespace);
    if (!entry) return null;

    // Update access stats
    entry.last_accessed_ms = Date.now();
    entry.access_count++;

    return entry.value;
  }

  private _set_cache(namespace: string, value: ParameterValue): void {
    const size = this._estimate_size(value);

    // Check if we need to evict
    while (this.cache_size_bytes + size > this.max_cache_bytes && this.cache.size > 0) {
      this._evict_lru_entry();
    }

    // Remove old entry size if exists
    const old_entry = this.cache.get(namespace);
    if (old_entry) {
      this.cache_size_bytes -= old_entry.size_bytes;
    }

    // Add new entry
    this.cache.set(namespace, {
      value,
      last_accessed_ms: Date.now(),
      access_count: 1,
      size_bytes: size
    });
    this.cache_size_bytes += size;
  }

  private _evict_lru_entry(): void {
    let lru_key: string | null = null;
    let lru_time = Infinity;

    for (const [key, entry] of this.cache.entries()) {
      if (entry.last_accessed_ms < lru_time) {
        lru_time = entry.last_accessed_ms;
        lru_key = key;
      }
    }

    if (lru_key) {
      const entry = this.cache.get(lru_key)!;
      this.cache_size_bytes -= entry.size_bytes;
      this.cache.delete(lru_key);
    }
  }

  private _evict_cache(): void {
    const now = Date.now();
    const stale_threshold = 5 * 60 * 1000; // 5 minutes

    for (const [key, entry] of this.cache.entries()) {
      if (now - entry.last_accessed_ms > stale_threshold && entry.access_count < 2) {
        this.cache_size_bytes -= entry.size_bytes;
        this.cache.delete(key);
      }
    }
  }

  private _estimate_size(value: ParameterValue): number {
    // Rough estimate of memory size
    if (value.value_type === 'vector' && Array.isArray(value.value)) {
      return value.value.length * 8 + 200; // 8 bytes per float64 + overhead
    }
    return JSON.stringify(value).length * 2 + 200; // UTF-16 + overhead
  }

  private _merge_values(existing: any, update: any): any {
    if (typeof existing === 'object' && typeof update === 'object' && 
        !Array.isArray(existing) && !Array.isArray(update)) {
      return { ...existing, ...update };
    }
    return update;
  }

  private _decompress(data: any): any {
    // Placeholder for decompression logic
    // In production, implement gzip or zstd decompression
    return data;
  }

  private async _health_check_shards(): Promise<void> {
    // Check shard health and update routing
    for (const [shard_key, routing] of this.shard_routing.entries()) {
      const start = Date.now();
      try {
        await this._fetch_from_cloud('/stats', {});
        routing.healthy = true;
        routing.latency_ms = Date.now() - start;
      } catch {
        routing.healthy = false;
      }
    }
  }
}

// Legacy compatibility - wrapper for v1 API
export class CloudParameterManagerV1Compat extends ScalableParameterManager {
  async getParameters(): Promise<Record<string, any>> {
    // Fetch common parameter patterns for backward compatibility
    const response = await this.fetchBatch({
      namespace_patterns: [
        'config.*',
        'model.default.*',
        'organ.default.*'
      ],
      max_results: 1000
    });

    // Flatten namespace structure for v1 compatibility
    const flattened: Record<string, any> = {};
    for (const [namespace, param] of Object.entries(response.parameters)) {
      const key = namespace.split('.').pop() || namespace;
      flattened[key] = param.value;
    }

    return flattened;
  }

  async updateParameters(updates: Record<string, any>): Promise<void> {
    const batch_updates: Record<string, any> = {};
    
    for (const [key, value] of Object.entries(updates)) {
      // Map flat keys to namespaced keys
      const namespace = this._infer_namespace(key);
      batch_updates[namespace] = {
        value,
        value_type: this._infer_type(value),
        metadata: { source: 'v1_compat' }
      };
    }

    await this.updateBatch({
      updates: batch_updates,
      strategy: 'merge'
    });
  }

  private _infer_namespace(key: string): string {
    // Infer namespace from key pattern
    if (key.includes('temperature') || key.includes('top_k') || key.includes('compute')) {
      return `config.generation.${key}`;
    }
    if (key.includes('risk') || key.includes('attention') || key.includes('organ')) {
      return `organ.chat.${key}`;
    }
    return `config.default.${key}`;
  }

  private _infer_type(value: any): ParameterValueType {
    if (typeof value === 'number') return 'float';
    if (Array.isArray(value) && typeof value[0] === 'number') return 'vector';
    return 'json';
  }
}
