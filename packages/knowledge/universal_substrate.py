#!/usr/bin/env python3
"""
Universal Parameter Layer — Standardized Substrate for Synthesus 2.0
AIVM LLC

Unifies access to:
1. Parameter Cloud V2 (PostgreSQL/Binary)
2. KAL (Knowledge Architecture Layer)
3. Smart FS (Local fallback and character-file compatibility)

Domains:
- left_hemisphere: Pattern lookups, token triggers, confidence scores (< 1ms).
- right_hemisphere: Cognitive memory, plans, personality, world-state.
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Union

import requests

log = logging.getLogger("universal_substrate")

class UniversalSubstrate:
    """
    Unified client for retrieving and storing parameters across all domains.
    Implements 'Smart FS' for low-latency local fallbacks.
    """

    def __init__(
        self,
        endpoint: str = "http://localhost:8000/parameter-cloud/v2",
        local_data_dir: str = "data",
        local_char_dir: str = "characters",
        knowledge_cloud_dir: str = "data/knowledge_cloud",
        cache_ttl_ms: int = 5000
    ):
        self.endpoint = endpoint.rstrip("/")
        self.local_data_dir = Path(local_data_dir)
        self.local_char_dir = Path(local_char_dir)
        self.knowledge_cloud_dir = Path(knowledge_cloud_dir)
        self.cache_ttl_ms = cache_ttl_ms
        self._cache: Dict[str, Dict[str, Any]] = {}
        
        # Ensure local directories exist
        self.local_data_dir.mkdir(parents=True, exist_ok=True)
        self.local_char_dir.mkdir(parents=True, exist_ok=True)
        self.knowledge_cloud_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def get_parameter(self, namespace: str, domain: str = "right_hemisphere") -> Optional[Dict[str, Any]]:
        """
        Retrieve a parameter from the cloud, with Smart FS fallback.
        """
        full_key = f"{domain}.{namespace}"
        
        # 1. Try Memory Cache
        cached = self._get_from_memory(full_key)
        if cached:
            return cached

        # 2. Try Cloud API (V2)
        try:
            resp = requests.post(
                f"{self.endpoint}/fetch-batch",
                json={"namespace_patterns": [full_key], "max_results": 1},
                timeout=0.1
            )
            if resp.status_code == 200:
                data = resp.json()
                params = data.get("parameters", {})
                if full_key in params:
                    val = params[full_key]
                    self._update_memory_cache(full_key, val)
                    return val
        except Exception as e:
            log.debug(f"Cloud fetch failed for {full_key}: {e}")

        # 3. Smart FS Fallback (Local Disk)
        return self._get_from_local_fs(namespace, domain)

    def set_parameter(
        self,
        namespace: str,
        value: Any,
        domain: str = "right_hemisphere",
        value_type: str = "json",
        metadata: Optional[Dict] = None
    ) -> bool:
        """
        Store a parameter in the cloud and sync to Smart FS.
        """
        full_key = f"{domain}.{namespace}"
        
        # 1. Update Memory Cache
        entry = {
            "value": value,
            "value_type": value_type,
            "metadata": metadata or {},
            "updated_at_ms": int(time.time() * 1000)
        }
        self._update_memory_cache(full_key, entry)

        # 2. Sync to Smart FS (Local persist)
        self._save_to_local_fs(namespace, domain, entry)

        # 3. Sync to Cloud (Fire and forget or async in production)
        try:
            requests.post(
                f"{self.endpoint}/update-batch",
                json={"updates": {full_key: entry}, "strategy": "merge"},
                timeout=2.0
            )
            return True
        except Exception as e:
            log.warning(f"Cloud sync failed for {full_key}: {e}")
            return False

    def batch_fetch(self, patterns: List[str], domain: str = "right_hemisphere") -> Dict[str, Any]:
        """
        Fetch multiple parameters matching patterns.
        """
        full_patterns = [f"{domain}.{p}" for p in patterns]
        
        try:
            resp = requests.post(
                f"{self.endpoint}/fetch-batch",
                json={"namespace_patterns": full_patterns, "max_results": 1000},
                timeout=5.0
            )
            if resp.status_code == 200:
                return resp.json().get("parameters", {})
        except Exception as e:
            log.warning(f"Batch cloud fetch failed: {e}")
        
        # Mock local batch fetch for patterns (incomplete but provides safety)
        return {}

    # ------------------------------------------------------------------
    # Internal: Smart FS
    # ------------------------------------------------------------------

    def _get_from_local_fs(self, namespace: str, domain: str) -> Optional[Dict[str, Any]]:
        """
        Retrieve from local character or data files.
        """
        # Example mapping: right_hemisphere.char_computress.bio -> characters/computress/bio.json
        parts = namespace.split('.')
        
        if domain == "right_hemisphere":
            if len(parts) >= 2 and parts[0].startswith("char_"):
                char_id = parts[0].replace("char_", "")
                attr = parts[1]
                path = self.local_char_dir / char_id / f"{attr}.json"
                if path.exists():
                    try:
                        with open(path, "r") as f:
                            return {"value": json.load(f), "value_type": "json"}
                    except: pass
        
        # Knowledge Cloud domain
        if domain == "knowledge_cloud":
            # namespace format: "entries" or "entry.{entity_id}"
            if namespace == "entries":
                # Return all entries from all JSON files
                all_entries = []
                if self.knowledge_cloud_dir.exists():
                    for json_file in self.knowledge_cloud_dir.glob("*.json"):
                        try:
                            with open(json_file, "r", encoding="utf-8") as f:
                                data = json.load(f)
                            entries = data if isinstance(data, list) else data.get("entries", [])
                            all_entries.extend(entries)
                        except: pass
                return {"value": all_entries, "value_type": "json"} if all_entries else None
        
        # Fallback for left_hemisphere or generic patterns
        return None

    def _save_to_local_fs(self, namespace: str, domain: str, entry: Dict[str, Any]):
        """
        Persist to local disk for 'Smart FS' durability.
        """
        parts = namespace.split('.')
        if domain == "right_hemisphere" and len(parts) >= 2 and parts[0].startswith("char_"):
            char_id = parts[0].replace("char_", "")
            attr = parts[1]
            char_path = self.local_char_dir / char_id
            char_path.mkdir(parents=True, exist_ok=True)
            
            path = char_path / f"{attr}.json"
            try:
                with open(path, "w") as f:
                    json.dump(entry["value"], f, indent=2)
            except Exception as e:
                log.error(f"Failed to save to Smart FS: {e}")

    # ------------------------------------------------------------------
    # Internal: Memory Cache
    # ------------------------------------------------------------------

    def _get_from_memory(self, full_key: str) -> Optional[Dict[str, Any]]:
        if full_key in self._cache:
            entry = self._cache[full_key]
            if (time.time() * 1000) - entry.get("_cached_at", 0) < self.cache_ttl_ms:
                return entry
        return None

    def _update_memory_cache(self, full_key: str, entry: Dict[str, Any]):
        entry["_cached_at"] = int(time.time() * 1000)
        self._cache[full_key] = entry
