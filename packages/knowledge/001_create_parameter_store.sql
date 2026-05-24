-- migrations/001_create_parameter_store.sql
-- Scalable parameter storage for billions of parameters

-- Main parameter table with partitioning support
CREATE TABLE IF NOT EXISTS parameters (
    id BIGSERIAL,
    namespace VARCHAR(500) NOT NULL,  -- e.g., "model.layers.0.attention.weights"
    shard_key VARCHAR(100) NOT NULL,  -- First 2 parts of namespace for sharding
    param_key VARCHAR(500) NOT NULL,  -- Full key path
    value_type VARCHAR(50) NOT NULL,  -- 'float', 'vector', 'sparse', 'json'
    scalar_value DOUBLE PRECISION,    -- For single float values
    vector_value VECTOR(1536),        -- For embeddings (pgvector)
    json_value JSONB,                 -- For complex structures
    metadata JSONB,                   -- Tags, version, last_updated, gradient_info
    version BIGINT NOT NULL DEFAULT 1,
    updated_at_ms BIGINT NOT NULL,
    created_at TIMESTAMP DEFAULT NOW(),
    
    PRIMARY KEY (shard_key, param_key)
) PARTITION BY LIST (shard_key);

-- Create default partition
CREATE TABLE parameters_default PARTITION OF parameters DEFAULT;

-- Indexes for efficient queries
CREATE INDEX idx_params_namespace ON parameters USING btree (namespace);
CREATE INDEX idx_params_metadata ON parameters USING gin (metadata);
CREATE INDEX idx_params_vector ON parameters USING hnsw (vector_value vector_cosine_ops)
    WHERE vector_value IS NOT NULL;
CREATE INDEX idx_params_updated ON parameters (updated_at_ms DESC);

-- Parameter groups/namespaces table for hierarchical organization
CREATE TABLE IF NOT EXISTS parameter_namespaces (
    namespace VARCHAR(500) PRIMARY KEY,
    shard_key VARCHAR(100) NOT NULL,
    parent_namespace VARCHAR(500),
    description TEXT,
    param_count BIGINT DEFAULT 0,
    total_size_bytes BIGINT DEFAULT 0,
    last_accessed_ms BIGINT,
    access_frequency BIGINT DEFAULT 0,
    importance_score DOUBLE PRECISION DEFAULT 1.0
);

CREATE INDEX idx_ns_shard ON parameter_namespaces(shard_key);
CREATE INDEX idx_ns_parent ON parameter_namespaces(parent_namespace);

-- Parameter gradients for LLM-style updates
CREATE TABLE IF NOT EXISTS parameter_gradients (
    id BIGSERIAL PRIMARY KEY,
    param_key VARCHAR(500) NOT NULL,
    shard_key VARCHAR(100) NOT NULL,
    gradient_vector VECTOR(1536),
    gradient_scalar DOUBLE PRECISION,
    learning_rate DOUBLE PRECISION DEFAULT 0.001,
    momentum DOUBLE PRECISION DEFAULT 0.9,
    step_count BIGINT DEFAULT 0,
    accumulated_ms BIGINT,
    applied_at_ms BIGINT,
    created_at TIMESTAMP DEFAULT NOW()
);

CREATE INDEX idx_gradients_param ON parameter_gradients(param_key, shard_key);
CREATE INDEX idx_gradients_pending ON parameter_gradients(accumulated_ms) 
    WHERE applied_at_ms IS NULL;

-- Metrics and performance tracking
CREATE TABLE IF NOT EXISTS parameter_metrics (
    id BIGSERIAL PRIMARY KEY,
    session_id VARCHAR(255),
    operation_type VARCHAR(50),  -- 'fetch', 'update', 'gradient_apply'
    namespace_pattern VARCHAR(500),
    param_count BIGINT,
    latency_ms DOUBLE PRECISION,
    cache_hit BOOLEAN DEFAULT FALSE,
    timestamp_ms BIGINT NOT NULL,
    metadata JSONB
);

CREATE INDEX idx_metrics_time ON parameter_metrics(timestamp_ms DESC);
CREATE INDEX idx_metrics_session ON parameter_metrics(session_id);

-- Function to auto-extract shard key from namespace
CREATE OR REPLACE FUNCTION extract_shard_key(namespace VARCHAR)
RETURNS VARCHAR AS $$
DECLARE
    parts TEXT[];
    result VARCHAR(100);
BEGIN
    parts := string_to_array(namespace, '.');
    IF array_length(parts, 1) >= 2 THEN
        result := parts[1] || '.' || parts[2];
    ELSE
        result := COALESCE(parts[1], 'default');
    END IF;
    RETURN result;
END;
$$ LANGUAGE plpgsql IMMUTABLE;

-- Trigger to auto-set shard_key
CREATE OR REPLACE FUNCTION set_shard_key()
RETURNS TRIGGER AS $$
BEGIN
    NEW.shard_key := extract_shard_key(NEW.namespace);
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER auto_shard_key
    BEFORE INSERT OR UPDATE ON parameters
    FOR EACH ROW
    EXECUTE FUNCTION set_shard_key();
