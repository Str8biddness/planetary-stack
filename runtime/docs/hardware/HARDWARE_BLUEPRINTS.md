# Hardware Blueprints for Synthesus 5 CHAL

## Overview

Hardware blueprints are declarative JSON/YAML templates that describe cluster topologies, resource pooling, and device mount configurations. Synthesus 5 generates these blueprints dynamically based on runtime conditions, then the CHAL layer instantiates them.

**Key Concept:** Instead of hardcoding cluster shapes, Synthesus generates blueprints that define:
- Physical node inventory (SSI resource nodes)
- Virtual resource pools (vCPU, vRAM, vGPU, vStorage)
- Network topology (master ↔ workers)
- Device mount points (chal://)
- Failover and degradation policies

---

## Blueprint Categories

### 1. Minimal Single-Node (Development)

For local testing without distributed resources.

```json
{
  "blueprint_id": "minimal-single",
  "version": "1.0",
  "timestamp": "2026-06-28T00:00:00Z",
  "category": "development",
  
  "cluster": {
    "name": "localhost-dev",
    "nodes": [
      {
        "node_id": "master",
        "role": "master",
        "hostname": "localhost",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 8,
          "ram_gb": 16,
          "gpu_vram_gb": 0,
          "disk_gb": 256,
          "simd_support": ["avx2"]
        }
      }
    ]
  },
  
  "vsource_devices": {
    "vcpu": {
      "enabled": true,
      "type": "local_executor",
      "max_concurrent_tasks": 4,
      "simd_backend": "avx2"
    },
    "vram": {
      "enabled": true,
      "type": "local_cache",
      "max_pages": 1000,
      "page_size_kb": 64
    },
    "vgpu": {
      "enabled": false
    },
    "vstorage": {
      "enabled": true,
      "type": "local_disk",
      "cache_blocks": 500,
      "prefetch_enabled": false
    }
  },
  
  "chal_mounts": [
    {
      "device": "chal://vsource/compute",
      "type": "vcpu_executor",
      "mount_point": "/dev/vsource/compute"
    },
    {
      "device": "chal://vsource/memory",
      "type": "vram_cache",
      "mount_point": "/dev/vsource/memory"
    },
    {
      "device": "chal://vsource/storage",
      "type": "vstorage_cache",
      "mount_point": "/dev/vsource/storage"
    }
  ]
}
```

---

### 2. Dual-Hemisphere Parallel Cluster

For N+1 redundancy with split-brain consciousness (left/right reasoning paths).

```json
{
  "blueprint_id": "dual-hemisphere",
  "version": "1.0",
  "timestamp": "2026-06-28T00:00:00Z",
  "category": "production",
  
  "cluster": {
    "name": "dual-hemisphere-cluster",
    "master_node": "master-primary",
    "failover_node": "master-backup",
    
    "nodes": [
      {
        "node_id": "master-primary",
        "role": "master",
        "hostname": "10.0.0.10",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 16,
          "ram_gb": 64,
          "gpu_vram_gb": 0,
          "disk_gb": 1024,
          "simd_support": ["avx2", "avx512"]
        }
      },
      {
        "node_id": "master-backup",
        "role": "master-backup",
        "hostname": "10.0.0.11",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 16,
          "ram_gb": 64,
          "gpu_vram_gb": 0,
          "disk_gb": 1024,
          "simd_support": ["avx2", "avx512"]
        }
      },
      {
        "node_id": "worker-left-hemi",
        "role": "reasoning_worker",
        "hemisphere": "left",
        "hostname": "10.0.1.20",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 32,
          "ram_gb": 128,
          "gpu_vram_gb": 24,
          "disk_gb": 2048,
          "simd_support": ["avx2", "avx512"]
        }
      },
      {
        "node_id": "worker-right-hemi",
        "role": "simulation_worker",
        "hemisphere": "right",
        "hostname": "10.0.1.21",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 32,
          "ram_gb": 128,
          "gpu_vram_gb": 24,
          "disk_gb": 2048,
          "simd_support": ["avx2", "avx512"]
        }
      }
    ]
  },
  
  "vsource_devices": {
    "vcpu": {
      "enabled": true,
      "type": "distributed_rpc",
      "task_queue_depth": 1024,
      "deadline_enforcement": true,
      "simd_backend": "avx512",
      "worker_selection": "load_aware"
    },
    "vram": {
      "enabled": true,
      "type": "distributed_cache",
      "max_pages": 100000,
      "page_size_kb": 64,
      "writeback_policy": "async_fire_and_forget",
      "cache_warmup": true
    },
    "vgpu": {
      "enabled": true,
      "type": "distributed_model_cache",
      "model_preload": true,
      "tensor_broadcast": "batched"
    },
    "vstorage": {
      "enabled": true,
      "type": "distributed_block_cache",
      "cache_blocks": 50000,
      "prefetch_enabled": true,
      "prefetch_policy": "sequential_detection"
    }
  },
  
  "hemisphere_routing": {
    "left_hemisphere": {
      "node": "worker-left-hemi",
      "role": "executive_reasoning",
      "chal_devices": ["chal://vsource/compute", "chal://knowledge/grounding"]
    },
    "right_hemisphere": {
      "node": "worker-right-hemi",
      "role": "cgpu_simulation",
      "chal_devices": ["chal://vsource/infer", "chal://vsource/storage"]
    }
  },
  
  "ssi_configuration": {
    "unified_storage": true,
    "storage_backend": "rclone",
    "storage_nodes": ["master-primary", "storage-expansion-1"],
    "mount_paths": [
      "/mnt/shared/models",
      "/mnt/shared/data",
      "/mnt/shared/logs"
    ]
  },
  
  "network_topology": {
    "backbone": "tcp",
    "heartbeat_interval_ms": 1000,
    "heartbeat_port": 7878,
    "control_plane_port": 9000,
    "data_plane_port": 9001
  },
  
  "chal_mounts": [
    {
      "device": "chal://vsource/compute",
      "type": "vcpu_distributed",
      "nodes": ["worker-left-hemi", "worker-right-hemi"],
      "mount_point": "/dev/vsource/compute"
    },
    {
      "device": "chal://vsource/memory",
      "type": "vram_distributed",
      "primary_node": "master-primary",
      "fallback_node": "master-backup",
      "mount_point": "/dev/vsource/memory"
    },
    {
      "device": "chal://vsource/infer",
      "type": "vgpu_distributed",
      "nodes": ["worker-left-hemi", "worker-right-hemi"],
      "model_registry": "/mnt/shared/models",
      "mount_point": "/dev/vsource/infer"
    },
    {
      "device": "chal://vsource/storage",
      "type": "vstorage_distributed",
      "nodes": ["worker-left-hemi", "worker-right-hemi"],
      "shared_mount": "/mnt/shared/data",
      "mount_point": "/dev/vsource/storage"
    }
  ]
}
```

---

### 3. Quad-Brain Compute Topology

Maps the four Synthesus 5 brains to dedicated compute nodes.

```json
{
  "blueprint_id": "quad-brain",
  "version": "1.0",
  "timestamp": "2026-06-28T00:00:00Z",
  "category": "production",
  
  "cluster": {
    "name": "quad-brain-cluster",
    "nodes": [
      {
        "node_id": "master",
        "role": "hypervisor",
        "hostname": "10.0.0.10",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 16,
          "ram_gb": 64,
          "disk_gb": 512
        }
      },
      {
        "node_id": "brain-1-knowledge",
        "role": "brain_grounding",
        "brain_id": 1,
        "hostname": "10.0.1.30",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 8,
          "ram_gb": 32,
          "disk_gb": 2048,
          "simd_support": ["avx2"]
        },
        "affinity": "knowledge_io"
      },
      {
        "node_id": "brain-2-executive",
        "role": "brain_reasoning",
        "brain_id": 2,
        "hostname": "10.0.1.31",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 16,
          "ram_gb": 64,
          "disk_gb": 1024,
          "simd_support": ["avx512"]
        },
        "affinity": "cpu_intensive"
      },
      {
        "node_id": "brain-3-cgpu",
        "role": "brain_cgpu",
        "brain_id": 3,
        "hostname": "10.0.1.32",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 32,
          "ram_gb": 128,
          "gpu_vram_gb": 80,
          "disk_gb": 1024,
          "simd_support": ["avx512"]
        },
        "affinity": "gpu_compute"
      },
      {
        "node_id": "brain-4-critic",
        "role": "brain_critic",
        "brain_id": 4,
        "hostname": "10.0.1.33",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 8,
          "ram_gb": 32,
          "disk_gb": 512,
          "simd_support": ["avx2"]
        },
        "affinity": "policy_checks"
      }
    ]
  },
  
  "brain_routing": {
    "brain_1": {
      "name": "Knowledge / Grounding",
      "node": "brain-1-knowledge",
      "inputs": ["user_query", "task_plan"],
      "outputs": ["evidence_frame", "provenance"],
      "chal_devices": ["chal://knowledge/grounding", "chal://vsource/storage"]
    },
    "brain_2": {
      "name": "Executive Reasoning",
      "node": "brain-2-executive",
      "inputs": ["user_query", "evidence_frame"],
      "outputs": ["execution_plan", "reasoning_frame"],
      "chal_devices": ["chal://vsource/compute", "chal://reasoning/executive"]
    },
    "brain_3": {
      "name": "CGPU Simulation",
      "node": "brain-3-cgpu",
      "inputs": ["evidence_frame", "execution_plan"],
      "outputs": ["response_candidates", "persona_frames"],
      "chal_devices": ["chal://vsource/infer", "chal://cgpu/render"]
    },
    "brain_4": {
      "name": "Critic / Safety",
      "node": "brain-4-critic",
      "inputs": ["evidence_frame", "reasoning_frame", "cgpu_candidates"],
      "outputs": ["critique_frame", "accept_or_rewrite", "safety_interrupt"],
      "chal_devices": ["chal://critic/hallucination_check", "chal://critic/template_leak"]
    }
  },
  
  "arbitration": {
    "type": "serialized_hemi_sync",
    "arbiter_node": "master",
    "merge_policy": "critic_weighted",
    "max_rewrite_passes": 1
  },
  
  "vsource_devices": {
    "vcpu": {
      "enabled": true,
      "worker_nodes": ["brain-2-executive"],
      "deadline_enforcement": true
    },
    "vram": {
      "enabled": true,
      "primary_node": "master",
      "cache_pages": 100000
    },
    "vgpu": {
      "enabled": true,
      "worker_nodes": ["brain-3-cgpu"],
      "model_preload": true
    },
    "vstorage": {
      "enabled": true,
      "worker_nodes": ["brain-1-knowledge"],
      "cache_blocks": 100000,
      "prefetch_enabled": true
    }
  }
}
```

---

### 4. Knowledge Cloud Hardware Mount

Mounts Knowledge Cloud partitions as virtual hardware through CHAL.

```json
{
  "blueprint_id": "knowledge-cloud-hardware",
  "version": "1.0",
  "timestamp": "2026-06-28T00:00:00Z",
  "category": "storage",
  
  "knowledge_cloud_partitions": {
    "rom": {
      "partition": "kc://rom/core-facts",
      "path": "/mnt/shared/knowledge/rom",
      "mount_mode": "read_only",
      "cache_policy": "warm_on_boot",
      "size_gb": 500
    },
    "parameters": {
      "partition": "kc://params/domain-routing",
      "path": "/mnt/shared/knowledge/params",
      "mount_mode": "read_only",
      "size_gb": 100
    },
    "cache": {
      "partition": "kc://cache/hot-retrievals",
      "path": "/mnt/shared/knowledge/cache",
      "mount_mode": "read_write",
      "cache_policy": "lru_evict",
      "size_gb": 200
    },
    "corpus": {
      "partition": "kc://corpus/grounding",
      "path": "/mnt/shared/knowledge/corpus",
      "mount_mode": "read_only",
      "embedding_dim": 768,
      "index_type": "faiss_ivf",
      "size_gb": 1000
    },
    "writeback": {
      "partition": "kc://memory/writeback",
      "path": "/mnt/shared/knowledge/writeback",
      "mount_mode": "read_write",
      "cache_policy": "critic_validated",
      "size_gb": 100
    }
  },
  
  "manifest_verification": {
    "enabled": true,
    "manifest_path": "/mnt/shared/knowledge/MANIFEST.json",
    "verify_on_boot": true,
    "hash_algorithm": "sha256",
    "degraded_mode_allowed": true
  },
  
  "chal_mounts": [
    {
      "device": "chal://knowledge/rom",
      "type": "kernel_memory",
      "partition": "kc://rom/core-facts",
      "mount_point": "/dev/knowledge/rom"
    },
    {
      "device": "chal://knowledge/params",
      "type": "parameter_disk",
      "partition": "kc://params/domain-routing",
      "mount_point": "/dev/knowledge/params"
    },
    {
      "device": "chal://knowledge/corpus",
      "type": "faiss_index",
      "partition": "kc://corpus/grounding",
      "mount_point": "/dev/knowledge/corpus"
    },
    {
      "device": "chal://memory/writeback",
      "type": "episodic_memory",
      "partition": "kc://memory/writeback",
      "mount_point": "/dev/memory/writeback"
    }
  ]
}
```

---

### 5. Degraded-Mode Cluster

Fallback blueprint when workers become unavailable.

```json
{
  "blueprint_id": "degraded-mode",
  "version": "1.0",
  "timestamp": "2026-06-28T00:00:00Z",
  "category": "failover",
  
  "cluster": {
    "name": "degraded-mode-cluster",
    "nodes": [
      {
        "node_id": "master",
        "role": "master_only",
        "hostname": "10.0.0.10",
        "tcp_port": 9000,
        "resources": {
          "cpu_cores": 16,
          "ram_gb": 64,
          "disk_gb": 1024
        }
      }
    ]
  },
  
  "vsource_devices": {
    "vcpu": {
      "enabled": true,
      "type": "local_executor_scaled_down",
      "max_concurrent_tasks": 1,
      "simd_backend": "scalar"
    },
    "vram": {
      "enabled": true,
      "type": "local_cache_reduced",
      "max_pages": 10000
    },
    "vgpu": {
      "enabled": false
    },
    "vstorage": {
      "enabled": true,
      "type": "local_disk",
      "cache_blocks": 5000,
      "prefetch_enabled": false
    }
  },
  
  "cognitive_hypervisor": {
    "mode": "degraded",
    "allowed_paths": ["fast_path"],
    "skip_paths": ["deep_quad_path", "cgpu_simulation"],
    "response_template_allowed": true,
    "max_latency_ms": 5000
  }
}
```

---

## Blueprint Generation Algorithm

Synthesus 5 generates blueprints dynamically using this algorithm:

```python
# packages/core/blueprint_generator.py

from dataclasses import dataclass
from typing import Dict, List
import json

@dataclass
class ClusterInventory:
    """Runtime cluster state from heartbeat broadcasts."""
    nodes: Dict[str, Dict]  # node_id -> {cpu_cores, ram_gb, gpu_vram_gb, ...}
    master_node: str
    timestamp: float

class BlueprintGenerator:
    """Generate CHAL hardware blueprints from cluster state."""
    
    def __init__(self):
        self.inventory: Optional[ClusterInventory] = None
    
    async def discover_cluster(self, heartbeat_port: int = 7878) -> ClusterInventory:
        """
        Discover available nodes via UDP heartbeat broadcasts.
        
        Returns inventory of all reachable nodes.
        """
        # TODO: Listen on heartbeat_port, collect advertised hardware
        pass
    
    def generate_blueprint(
        self,
        inventory: ClusterInventory,
        topology: str = "auto"
    ) -> Dict:
        """
        Generate hardware blueprint from cluster inventory.
        
        topology options:
          - "minimal": single-node dev
          - "dual-hemisphere": N+1 with left/right parallelism
          - "quad-brain": 4 brains + hypervisor
          - "auto": pick based on node count and capabilities
        """
        if topology == "auto":
            topology = self._select_topology(inventory)
        
        if topology == "minimal":
            return self._generate_minimal_blueprint(inventory)
        elif topology == "dual-hemisphere":
            return self._generate_dual_hemisphere_blueprint(inventory)
        elif topology == "quad-brain":
            return self._generate_quad_brain_blueprint(inventory)
        else:
            raise ValueError(f"Unknown topology: {topology}")
    
    def _select_topology(self, inventory: ClusterInventory) -> str:
        """Auto-select topology based on node count and resources."""
        node_count = len(inventory.nodes)
        
        if node_count == 1:
            return "minimal"
        elif node_count <= 4:
            return "dual-hemisphere"
        else:
            return "quad-brain"
    
    def _generate_minimal_blueprint(self, inventory: ClusterInventory) -> Dict:
        """Generate single-node development blueprint."""
        master = list(inventory.nodes.values())[0]
        
        return {
            "blueprint_id": "minimal-generated",
            "timestamp": inventory.timestamp,
            "cluster": {
                "nodes": [
                    {
                        "node_id": "master",
                        "role": "master",
                        "hostname": master["hostname"],
                        "resources": master
                    }
                ]
            },
            # ... simplified vsource_devices
        }
    
    def _generate_dual_hemisphere_blueprint(self, inventory: ClusterInventory) -> Dict:
        """Generate dual-hemisphere blueprint from available nodes."""
        nodes_list = list(inventory.nodes.items())
        
        # Designate first as master, rest as workers
        master_id, master_node = nodes_list[0]
        
        # Assign remaining nodes to hemispheres
        left_hemi = nodes_list[1] if len(nodes_list) > 1 else None
        right_hemi = nodes_list[2] if len(nodes_list) > 2 else None
        
        return {
            "blueprint_id": "dual-hemisphere-generated",
            "timestamp": inventory.timestamp,
            # ... full blueprint with master + hemisphere workers
        }
    
    def _generate_quad_brain_blueprint(self, inventory: ClusterInventory) -> Dict:
        """Generate quad-brain blueprint from available nodes."""
        nodes_list = list(inventory.nodes.items())
        
        # Map first 5 nodes to: master + 4 brains
        master_id = nodes_list[0][0]
        brain_nodes = nodes_list[1:5] if len(nodes_list) >= 5 else []
        
        return {
            "blueprint_id": "quad-brain-generated",
            "timestamp": inventory.timestamp,
            # ... full blueprint with master + 4 brain workers
        }
```

---

## Integration with CHAL

Blueprints are loaded at hypervisor boot:

```python
# packages/core/cognitive_hypervisor.py (excerpt)

class CognitiveHypervisor:
    
    async def boot(self, blueprint_path: str = None) -> None:
        """Boot the hypervisor with a hardware blueprint."""
        
        if blueprint_path is None:
            # Auto-discover cluster and generate blueprint
            inventory = await self.blueprint_gen.discover_cluster()
            blueprint = self.blueprint_gen.generate_blueprint(inventory)
        else:
            # Load blueprint from file
            with open(blueprint_path) as f:
                blueprint = json.load(f)
        
        # Mount all CHAL devices from blueprint
        for mount in blueprint["chal_mounts"]:
            await self.chal_bus.mount_device(
                device_address=mount["device"],
                device_type=mount["type"],
                mount_point=mount["mount_point"],
                config=mount.get("config", {})
            )
        
        print(f"✓ Hypervisor booted with blueprint: {blueprint['blueprint_id']}")
```

---

## Reference Files

- `docs/hardware/VSOURCE_ABSTRACTION_LAYER.md` — vCPU, vRAM, vGPU, vStorage design
- `docs/hardware/SSI_CLUSTER_ARCHITECTURE.md` — Single System Image implementation
- `packages/core/blueprint_generator.py` — Blueprint generation algorithm
- `packages/core/cognitive_hypervisor.py` — Hypervisor boot and device mounting

---

## Next Steps

1. **Synthesus Blueprint Synthesis**: Use Synthesus 5 to generate blueprints from natural language cluster descriptions.
2. **Validation Testing**: Deploy generated blueprints to test clusters and verify CHAL device mounting.
3. **Optimization**: Auto-tune blueprint parameters (cache sizes, prefetch policies, deadline budgets) based on workload profiling.
