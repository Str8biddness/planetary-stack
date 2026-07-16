# SCALING_TO_BILLIONS.md
# Scaling Synthesus Parameter Cloud to Billions of Parameters

**STATUS: DESIGN — NOT YET VALIDATED**

## Architecture Overview

The scalable Parameter Cloud V2 is designed to handle billions of parameters across distributed shards.

### Key Components

1. **Database Layer** - PostgreSQL with pgvector extension
   - Partitioned tables by `shard_key` for horizontal scaling
   - HNSW indexes for vector similarity search
   - GIN indexes for metadata queries

2. **API Layer** - FastAPI with V2 endpoints
   - `/fetch-batch` - Pattern-based batch fetching
   - `/query` - Advanced filtering with vector search
   - `/update-batch` - Batch updates with gradient support
   - `/apply-gradients` - Background gradient application

3. **Client Layer** - TypeScript ScalableParameterManager
   - LRU cache with size-based eviction
   - Connection pooling and retry logic
   - Streaming for large datasets
   - Background prefetching

## Quick Start

### 1. Setup PostgreSQL with pgvector

```bash
# Install PostgreSQL 14+ with pgvector extension
docker run -d \
  --name synthesus-db \
  -e POSTGRES_USER=synthesus \
  -e POSTGRES_PASSWORD=synthesus \
  -e POSTGRES_DB=synthesus_params \
  -p 5432:5432 \
  ankane/pgvector:latest

# Run migrations
psql -h localhost -U synthesus -d synthesus_params -f migrations/001_create_parameter_store.sql
```

### 2. Configure Shards

```bash
# Set environment variable for shard configuration
export PARAMETER_SHARDS="model.layers:localhost:5432:2.0,organ.chat:localhost:5432:1.5,config:localhost:5432:1.0"
```

### 3. Mount V2 Router

```python
# api/production_server.py
from api.parameter_cloud_v2 import router as parameter_cloud_v2_router

# Mount alongside V1 for backward compatibility
app.include_router(parameter_cloud_v2_router)
```

### 4. Use Scalable Client

```typescript
import { ScalableParameterManager } from './utils/cloudParametersV2';

const manager = new ScalableParameterManager({
  cloud_endpoint: 'http://localhost:5010/parameter-cloud/v2',
  api_key: 'your-api-key',
  local_cache_max_mb: 500,        // 500MB local cache
  batch_fetch_size: 50000,        // Fetch 50k params at a time
  prefetch_patterns: [             // Preload critical parameters
    'model.layers.*',
    'organ.chat.policy*'
  ],
  compression_enabled: true,
  connection_pool_size: 20,
  fetch_timeout_ms: 60000,
  retry_attempts: 5
});

// Fetch billions of parameters efficiently
const modelWeights = await manager.fetchBatch({
  namespace_patterns: ['model.layers.*', 'organ.*'],
  max_results: 100000
});

// Stream through all parameters (memory-efficient)
for await (const param of manager.streamParameters('model.layers.*', 1000)) {
  // Process each parameter
  console.log(param.namespace, param.value);
}

// Batch update with gradients (LLM-style training)
await manager.updateBatch({
  updates: {
    'model.layers.0.attention.weights': {
      value: gradientVector,
      value_type: 'vector'
    }
  },
  strategy: 'gradient',
  learning_rate: 0.001
});
```

## Migration from V1

### Automatic Migration

```python
# migration_script.py
import asyncio
import json
from api.parameter_cloud import _load_store
from api.parameter_cloud_v2 import update_batch_params, get_db_pool

async def migrate_v1_to_v2():
    # Load V1 data
    v1_data = _load_store()
    parameters = v1_data.get('parameters', {})
    
    # Convert to V2 format
    v2_updates = {}
    for key, value in parameters.items():
        # Infer namespace and type
        namespace = f"config.legacy.{key}"
        value_type = infer_type(value)
        v2_updates[namespace] = {
            'value': value,
            'value_type': value_type,
            'metadata': {'migrated_from': 'v1'}
        }
    
    # Batch insert into V2
    pool = await get_db_pool()
    await update_batch_params(
        BatchParameterUpdate(updates=v2_updates, strategy='replace'),
        pool
    )
    
    print(f"Migrated {len(v2_updates)} parameters")

def infer_type(value):
    if isinstance(value, (int, float)):
        return 'float'
    if isinstance(value, list) and len(value) > 0 and isinstance(value[0], (int, float)):
        return 'vector'
    return 'json'

if __name__ == '__main__':
    asyncio.run(migrate_v1_to_v2())
```

## Scaling Strategies

### Horizontal Scaling (Multiple PostgreSQL Instances)

```bash
# Shard 0: Model weights
export PARAMETER_SHARDS="model.layers:db-shard-0.internal:5432:3.0"

# Shard 1: Organ parameters
export PARAMETER_SHARDS="organ.chat:db-shard-1.internal:5432:2.0,organ.gm:db-shard-1.internal:5432:2.0"

# Shard 2: Configuration
export PARAMETER_SHARDS="config:db-shard-2.internal:5432:1.0"
```

### Read Replicas

For read-heavy workloads (inference), configure read replicas:

```typescript
const manager = new ScalableParameterManager({
  cloud_endpoint: 'http://load-balancer/parameter-cloud/v2',
  read_replica_endpoints: [
    'http://replica-1/parameter-cloud/v2',
    'http://replica-2/parameter-cloud/v2'
  ],
  read_from_replicas: true
});
```

### Hot Parameter Caching with Redis

For frequently accessed parameters, add Redis layer:

```python
# api/parameter_cloud_v2.py - add Redis caching
import redis

redis_client = redis.Redis(host='redis-cache', port=6379, db=0)

async def fetch_with_cache(namespace: str):
    # Check Redis first
    cached = redis_client.get(f"param:{namespace}")
    if cached:
        return json.loads(cached)
    
    # Fetch from DB
    value = await fetch_from_db(namespace)
    
    # Cache in Redis (TTL based on access frequency)
    ttl = calculate_ttl(namespace)
    redis_client.setex(f"param:{namespace}", ttl, json.dumps(value))
    
    return value
```

## Performance Benchmarks

Expected performance with proper sharding:

| Metric | 1M params | 100M params | 1B params |
|--------|-----------|-------------|-----------|
| Fetch by pattern | 50ms | 100ms | 200ms |
| Single get (cached) | 0.1ms | 0.1ms | 0.1ms |
| Batch update (1k) | 100ms | 100ms | 100ms |
| Full scan | 2s | 30s | 5min |
| Vector search | 10ms | 50ms | 100ms |

## Monitoring

```sql
-- Query to monitor shard distribution
SELECT 
    shard_key,
    COUNT(*) as param_count,
    pg_size_pretty(SUM(pg_column_size(vector_value) + pg_column_size(json_value))) as total_size,
    AVG(updated_at_ms - LAG(updated_at_ms) OVER (ORDER BY updated_at_ms)) as avg_update_interval
FROM parameters
GROUP BY shard_key;

-- Identify hot parameters
SELECT 
    namespace,
    (metadata->>'access_count')::int as accesses,
    updated_at_ms
FROM parameters
WHERE (metadata->>'access_count')::int > 1000
ORDER BY accesses DESC
LIMIT 100;
```

## Best Practices

1. **Namespace Design**: Use hierarchical namespaces
   - `model.layers.{layer_id}.{component}.{param_type}`
   - `organ.{domain}.{organ_name}.{param_name}`
   - `config.{category}.{setting_name}`

2. **Batch Operations**: Always use batch operations
   - Batch size: 1,000 - 50,000 parameters
   - Pattern-based fetching instead of individual gets

3. **Caching Strategy**: 
   - Cache hot parameters (frequently accessed)
   - Don't cache large vectors unless necessary
   - Use TTL based on update frequency

4. **Gradient Updates**:
   - Accumulate gradients locally
   - Apply in batches every N steps
   - Use momentum for stability

5. **Database Maintenance**:
   - Partition by `shard_key`
   - Vacuum analyze regularly
   - Archive old gradient records
