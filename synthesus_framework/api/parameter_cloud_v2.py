# api/parameter_cloud_v2.py
# Scalable Parameter Cloud for billions of parameters
# Supports sharding, batching, and efficient querying

import os
import json
import asyncpg
from typing import Dict, List, Optional, Any, Tuple
from dataclasses import dataclass
from datetime import datetime
from fastapi import APIRouter, HTTPException, Query, Depends
from pydantic import BaseModel, Field
import hashlib
import struct

router = APIRouter(prefix="/parameter-cloud/v2", tags=["parameter-cloud-v2"])

# Database connection pool
_pool: Optional[asyncpg.Pool] = None

async def get_db_pool() -> asyncpg.Pool:
    global _pool
    if _pool is None:
        dsn = os.environ.get(
            "DATABASE_URL",
            "postgresql://synthesus:synthesus@localhost:5432/synthesus_params"
        )
        _pool = await asyncpg.create_pool(
            dsn=dsn,
            min_size=5,
            max_size=50,
            command_timeout=60
        )
    return _pool

@dataclass
class ParameterShard:
    """Represents a parameter shard for distributed storage"""
    shard_key: str
    host: str
    port: int
    weight: float = 1.0  # For weighted routing

class ParameterValue(BaseModel):
    """Single parameter value with type information"""
    value: Any
    value_type: str = Field(..., pattern="^(float|vector|sparse|json)$")
    metadata: Optional[Dict] = None
    version: int = 1

class BatchParameterFetch(BaseModel):
    """Request to fetch multiple parameters by pattern"""
    namespace_patterns: List[str] = Field(..., description="List of namespace patterns (e.g. ['model.layers.*', 'organ.chat.*'])")
    include_metadata: bool = True
    max_results: int = Field(10000, le=100000)
    cursor: Optional[str] = None  # For pagination

class BatchParameterUpdate(BaseModel):
    """Batch update multiple parameters"""
    updates: Dict[str, ParameterValue]
    strategy: str = Field("merge", pattern="^(merge|replace|gradient)$")
    learning_rate: Optional[float] = None  # For gradient updates
    
class ParameterQuery(BaseModel):
    """Advanced parameter query with filtering"""
    namespace_prefix: Optional[str] = None
    tags: Optional[List[str]] = None
    min_importance: Optional[float] = None
    updated_after_ms: Optional[int] = None
    vector_similarity: Optional[Tuple[List[float], float]] = None  # (vector, threshold)
    limit: int = Field(1000, le=10000)
    cursor: Optional[str] = None

class ShardedParameterStore:
    """Manages distributed parameter storage across shards"""
    
    def __init__(self):
        self.shards: Dict[str, ParameterShard] = {}
        self.shard_ring: List[Tuple[int, str]] = []  # Consistent hashing ring
        self._init_shards_from_env()
    
    def _init_shards_from_env(self):
        """Initialize shards from environment configuration"""
        # Format: SHARD_0=model.layers:localhost:5433:1.0,SHARD_1=organ.chat:localhost:5434:1.0
        shard_configs = os.environ.get("PARAMETER_SHARDS", "default:localhost:5432:1.0")
        
        for config in shard_configs.split(","):
            parts = config.strip().split(":")
            if len(parts) >= 3:
                shard_key = parts[0]
                host = parts[1]
                port = int(parts[2])
                weight = float(parts[3]) if len(parts) > 3 else 1.0
                
                shard = ParameterShard(shard_key, host, port, weight)
                self.shards[shard_key] = shard
                
                # Add to consistent hashing ring
                for i in range(int(weight * 100)):
                    hash_val = self._hash(f"{shard_key}:{i}")
                    self.shard_ring.append((hash_val, shard_key))
        
        self.shard_ring.sort()
    
    def _hash(self, key: str) -> int:
        """Consistent hash for key distribution"""
        return int(hashlib.md5(key.encode()).hexdigest(), 16)
    
    def get_shard_for_key(self, namespace: str) -> str:
        """Determine which shard owns a given namespace"""
        if not self.shard_ring:
            return "default"
        
        key_hash = self._hash(namespace)
        
        # Find first shard with hash >= key_hash
        for shard_hash, shard_key in self.shard_ring:
            if shard_hash >= key_hash:
                return shard_key
        
        # Wrap around to first shard
        return self.shard_ring[0][1]
    
    def get_shards_for_patterns(self, patterns: List[str]) -> List[str]:
        """Get all shards that might contain parameters matching patterns"""
        # For now, query all shards. In production, use namespace metadata
        return list(self.shards.keys())

# Global sharded store
sharded_store = ShardedParameterStore()

@router.post("/fetch-batch")
async def fetch_batch_params(
    request: BatchParameterFetch,
    pool: asyncpg.Pool = Depends(get_db_pool)
) -> Dict:
    """Fetch parameters matching namespace patterns across shards"""
    
    all_params = {}
    total_fetched = 0
    
    # Determine shards to query
    shards = sharded_store.get_shards_for_patterns(request.namespace_patterns)
    
    async with pool.acquire() as conn:
        for shard_key in shards:
            # Build query for this shard
            conditions = []
            params = []
            
            for pattern in request.namespace_patterns:
                # Convert glob pattern to SQL LIKE
                like_pattern = pattern.replace("*", "%").replace("?", "_")
                conditions.append("namespace LIKE $" + str(len(params) + 1))
                params.append(like_pattern)
            
            where_clause = " OR ".join(conditions) if conditions else "TRUE"
            
            # Add cursor pagination
            if request.cursor:
                where_clause += f" AND (namespace, param_key) > (${len(params) + 1}, ${len(params) + 2})"
                cursor_parts = request.cursor.split("||")
                params.extend(cursor_parts)
            
            query = f"""
                SELECT namespace, param_key, value_type, scalar_value, vector_value, json_value,
                       metadata, version, updated_at_ms
                FROM parameters
                WHERE shard_key = $1 AND ({where_clause})
                ORDER BY namespace, param_key
                LIMIT ${len(params) + 1}
            """
            
            rows = await conn.fetch(query, shard_key, *params, request.max_results)
            
            for row in rows:
                key = row['namespace']
                value = _deserialize_value(row)
                
                all_params[key] = {
                    "value": value,
                    "value_type": row['value_type'],
                    "version": row['version'],
                    "updated_at_ms": row['updated_at_ms'],
                    "metadata": json.loads(row['metadata']) if request.include_metadata and row['metadata'] else None
                }
                total_fetched += 1
        
        # Generate next cursor
        next_cursor = None
        if rows and len(rows) == request.max_results:
            last_row = rows[-1]
            next_cursor = f"{last_row['namespace']}||{last_row['param_key']}"
    
    return {
        "parameters": all_params,
        "count": total_fetched,
        "cursor": next_cursor,
        "version": int(datetime.now().timestamp() * 1000)
    }

@router.post("/query")
async def query_params(
    request: ParameterQuery,
    pool: asyncpg.Pool = Depends(get_db_pool)
) -> Dict:
    """Advanced parameter query with filtering and vector search"""
    
    conditions = ["TRUE"]
    params = []
    
    if request.namespace_prefix:
        conditions.append("namespace LIKE $" + str(len(params) + 1))
        params.append(f"{request.namespace_prefix}%")
    
    if request.tags:
        # GIN index query on metadata tags
        conditions.append("metadata @> $" + str(len(params) + 1))
        params.append(json.dumps({"tags": request.tags}))
    
    if request.min_importance:
        conditions.append("(metadata->>'importance')::float >= $" + str(len(params) + 1))
        params.append(str(request.min_importance))
    
    if request.updated_after_ms:
        conditions.append("updated_at_ms > $" + str(len(params) + 1))
        params.append(request.updated_after_ms)
    
    # Vector similarity search (using pgvector)
    vector_condition = ""
    if request.vector_similarity:
        query_vector, threshold = request.vector_similarity
        vector_condition = f"AND vector_value <=> ${len(params) + 1}::vector < {1 - threshold}"
        params.append(query_vector)
    
    where_clause = " AND ".join(conditions)
    
    async with pool.acquire() as conn:
        # For vector search, use HNSW index
        if request.vector_similarity:
            query = f"""
                SELECT namespace, param_key, value_type, scalar_value, vector_value, json_value,
                       metadata, version, updated_at_ms,
                       vector_value <=> ${len(params)}::vector as distance
                FROM parameters
                WHERE {where_clause} {vector_condition}
                ORDER BY vector_value <=> ${len(params)}::vector
                LIMIT ${len(params) + 1}
            """
        else:
            query = f"""
                SELECT namespace, param_key, value_type, scalar_value, vector_value, json_value,
                       metadata, version, updated_at_ms
                FROM parameters
                WHERE {where_clause}
                ORDER BY updated_at_ms DESC
                LIMIT ${len(params) + 1}
            """
        
        rows = await conn.fetch(query, *params, request.limit)
        
        results = []
        for row in rows:
            result = {
                "namespace": row['namespace'],
                "key": row['param_key'],
                "value": _deserialize_value(row),
                "value_type": row['value_type'],
                "version": row['version'],
                "updated_at_ms": row['updated_at_ms']
            }
            if request.vector_similarity:
                result['similarity'] = 1 - row['distance']
            results.append(result)
    
    return {
        "results": results,
        "count": len(results)
    }

@router.post("/update-batch")
async def update_batch_params(
    request: BatchParameterUpdate,
    pool: asyncpg.Pool = Depends(get_db_pool)
) -> Dict:
    """Batch update parameters with merge/replace/gradient strategies"""
    
    updated_count = 0
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    
    async with pool.acquire() as conn:
        async with conn.transaction():
            for namespace, param_value in request.updates.items():
                shard_key = sharded_store.get_shard_for_key(namespace)
                
                if request.strategy == "gradient" and request.learning_rate:
                    # Store gradient for later application
                    await _store_gradient(conn, namespace, shard_key, param_value, request.learning_rate, timestamp_ms)
                else:
                    # Direct update
                    await _upsert_parameter(conn, namespace, shard_key, param_value, request.strategy, timestamp_ms)
                
                updated_count += 1
    
    return {
        "updated": updated_count,
        "version": timestamp_ms,
        "strategy": request.strategy
    }

async def _upsert_parameter(conn, namespace: str, shard_key: str, param_value: ParameterValue, strategy: str, timestamp_ms: int):
    """Insert or update a single parameter"""
    
    serialized = _serialize_value(param_value.value, param_value.value_type)
    
    if strategy == "replace":
        # Full replace
        await conn.execute("""
            INSERT INTO parameters (namespace, shard_key, param_key, value_type, scalar_value, 
                                   vector_value, json_value, metadata, version, updated_at_ms)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, $9, $10)
            ON CONFLICT (shard_key, param_key) 
            DO UPDATE SET
                value_type = EXCLUDED.value_type,
                scalar_value = EXCLUDED.scalar_value,
                vector_value = EXCLUDED.vector_value,
                json_value = EXCLUDED.json_value,
                metadata = EXCLUDED.metadata,
                version = parameters.version + 1,
                updated_at_ms = EXCLUDED.updated_at_ms
        """, namespace, shard_key, namespace, param_value.value_type,
            serialized.get('scalar'), serialized.get('vector'), serialized.get('json'),
            json.dumps(param_value.metadata), param_value.version, timestamp_ms)
    else:
        # Merge - only update provided fields
        existing = await conn.fetchrow(
            "SELECT * FROM parameters WHERE shard_key = $1 AND param_key = $2",
            shard_key, namespace
        )
        
        if existing:
            # Merge with existing
            new_value = _merge_values(
                _deserialize_value(existing),
                param_value.value,
                param_value.value_type
            )
            serialized = _serialize_value(new_value, param_value.value_type)
        
        await conn.execute("""
            INSERT INTO parameters (namespace, shard_key, param_key, value_type, scalar_value,
                                   vector_value, json_value, metadata, version, updated_at_ms)
            VALUES ($1, $2, $3, $4, $5, $6, $7, $8, COALESCE($9, 1), $10)
            ON CONFLICT (shard_key, param_key)
            DO UPDATE SET
                scalar_value = COALESCE(EXCLUDED.scalar_value, parameters.scalar_value),
                vector_value = COALESCE(EXCLUDED.vector_value, parameters.vector_value),
                json_value = COALESCE(EXCLUDED.json_value, parameters.json_value),
                metadata = COALESCE(EXCLUDED.metadata, parameters.metadata),
                version = parameters.version + 1,
                updated_at_ms = EXCLUDED.updated_at_ms
        """, namespace, shard_key, namespace, param_value.value_type,
            serialized.get('scalar'), serialized.get('vector'), serialized.get('json'),
            json.dumps(param_value.metadata), param_value.version, timestamp_ms)

async def _store_gradient(conn, namespace: str, shard_key: str, param_value: ParameterValue, learning_rate: float, timestamp_ms: int):
    """Store gradient for later batch application"""
    
    serialized = _serialize_value(param_value.value, param_value.value_type)
    
    await conn.execute("""
        INSERT INTO parameter_gradients (param_key, shard_key, gradient_vector, gradient_scalar,
                                        learning_rate, accumulated_ms)
        VALUES ($1, $2, $3, $4, $5, $6)
    """, namespace, shard_key, serialized.get('vector'), serialized.get('scalar'), 
        learning_rate, timestamp_ms)

@router.post("/apply-gradients")
async def apply_gradients(
    max_gradients: int = 10000,
    pool: asyncpg.Pool = Depends(get_db_pool)
) -> Dict:
    """Apply accumulated gradients to parameters (background batch job)"""
    
    applied_count = 0
    timestamp_ms = int(datetime.now().timestamp() * 1000)
    
    async with pool.acquire() as conn:
        # Fetch pending gradients
        gradients = await conn.fetch("""
            SELECT param_key, shard_key, gradient_vector, gradient_scalar, learning_rate, momentum
            FROM parameter_gradients
            WHERE applied_at_ms IS NULL
            ORDER BY accumulated_ms
            LIMIT $1
        """, max_gradients)
        
        for grad in gradients:
            # Fetch current parameter
            param = await conn.fetchrow("""
                SELECT * FROM parameters 
                WHERE shard_key = $1 AND param_key = $2
            """, grad['shard_key'], grad['param_key'])
            
            if param:
                # Apply gradient update
                current_value = _deserialize_value(param)
                
                if grad['gradient_vector'] is not None:
                    # Vector update: w_new = w_old - lr * grad
                    new_vector = [
                        w - grad['learning_rate'] * g 
                        for w, g in zip(current_value, grad['gradient_vector'])
                    ]
                    await conn.execute("""
                        UPDATE parameters 
                        SET vector_value = $1::vector, version = version + 1, updated_at_ms = $2
                        WHERE shard_key = $3 AND param_key = $4
                    """, new_vector, timestamp_ms, grad['shard_key'], grad['param_key'])
                else:
                    # Scalar update
                    new_scalar = current_value - grad['learning_rate'] * grad['gradient_scalar']
                    await conn.execute("""
                        UPDATE parameters 
                        SET scalar_value = $1, version = version + 1, updated_at_ms = $2
                        WHERE shard_key = $3 AND param_key = $4
                    """, new_scalar, timestamp_ms, grad['shard_key'], grad['param_key'])
                
                applied_count += 1
            
            # Mark gradient as applied
            await conn.execute("""
                UPDATE parameter_gradients 
                SET applied_at_ms = $1 
                WHERE param_key = $2 AND shard_key = $3 AND applied_at_ms IS NULL
            """, timestamp_ms, grad['param_key'], grad['shard_key'])
    
    return {"applied": applied_count, "timestamp_ms": timestamp_ms}

@router.get("/shards")
async def list_shards() -> Dict:
    """List all configured shards"""
    return {
        "shards": [
            {
                "shard_key": shard.shard_key,
                "host": shard.host,
                "port": shard.port,
                "weight": shard.weight
            }
            for shard in sharded_store.shards.values()
        ]
    }

@router.get("/stats")
async def get_stats(pool: asyncpg.Pool = Depends(get_db_pool)) -> Dict:
    """Get parameter storage statistics"""
    
    stats_path = os.path.join(os.path.dirname(__file__), "..", "data", "parameter_cloud_v2_stats.json")
    if os.path.exists(stats_path):
        with open(stats_path, "r") as f:
            v2_stats = json.load(f)
            return {
                "total_parameters": v2_stats["total_parameters"],
                "total_entries": v2_stats["total_entries"],
                "vector_dimension": v2_stats["vector_dimension"],
                "shards": v2_stats["shards"],
                "status": v2_stats["status"],
                "version": v2_stats["ingested_at"]
            }

    async with pool.acquire() as conn:
        total_params = await conn.fetchval("SELECT COUNT(*) FROM parameters")
        total_namespaces = await conn.fetchval("SELECT COUNT(DISTINCT namespace) FROM parameters")
        
        shard_stats = await conn.fetch("""
            SELECT shard_key, COUNT(*) as param_count, 
                   SUM(pg_column_size(vector_value) + pg_column_size(json_value)) as total_size
            FROM parameters
            GROUP BY shard_key
        """)
    
    return {
        "total_parameters": total_params,
        "total_namespaces": total_namespaces,
        "shards": [
            {
                "shard_key": row['shard_key'],
                "param_count": row['param_count'],
                "size_bytes": row['total_size'] or 0
            }
            for row in shard_stats
        ]
    }

def _serialize_value(value: Any, value_type: str) -> Dict:
    """Serialize value for database storage"""
    result = {}
    
    if value_type == "float":
        result['scalar'] = float(value)
    elif value_type == "vector":
        result['vector'] = [float(v) for v in value]
    elif value_type == "sparse":
        result['json'] = {"sparse": value}
    elif value_type == "json":
        result['json'] = value if isinstance(value, dict) else {"value": value}
    
    return result

def _deserialize_value(row) -> Any:
    """Deserialize value from database row"""
    
    if row['scalar_value'] is not None:
        return row['scalar_value']
    elif row['vector_value'] is not None:
        return [float(v) for v in row['vector_value']]
    elif row['json_value'] is not None:
        json_val = row['json_value']
        if isinstance(json_val, str):
            json_val = json.loads(json_val)
        if isinstance(json_val, dict) and 'sparse' in json_val:
            return json_val['sparse']
        return json_val
    return None

def _merge_values(existing: Any, new: Any, value_type: str) -> Any:
    """Merge two values based on type"""
    
    if value_type == "json" or value_type == "sparse":
        if isinstance(existing, dict) and isinstance(new, dict):
            merged = existing.copy()
            merged.update(new)
            return merged
    
    return new
