#!/usr/bin/env python3
"""
Mirror Sync Bridge for AIOS
AIVM LLC - Phase 4 Cluster Synchronization

Bridges the background mirror sync daemon to the Virtual Mirror Device (VMD).
"""

from __future__ import annotations

import logging
import os
import json
import threading
import time
from pathlib import Path
from typing import Any, Dict, List, Optional, Callable

# Add mirror-sync-system to path
MIRROR_SRC = Path("/home/dakin/Desktop/mirror-sync-system")
import sys
if str(MIRROR_SRC) not in sys.path:
    sys.path.insert(0, str(MIRROR_SRC))

try:
    from mirror_sync_daemon import run_sync_command, load_config
except ImportError:
    logger = logging.getLogger(__name__)
    logger.error("Mirror sync system not found at %s", MIRROR_SRC)

logger = logging.getLogger("synthesus.aios.mirror")

class MirrorSyncBridge:
    """Bridges the AIOS VMD to the host mirror-sync-daemon."""

    def __init__(self, config_path: str = "/home/dakin/.mirror_sync_config.json"):
        self.config_path = Path(config_path)
        self._ensure_config()
        self._sync_thread = None
        self._on_state_change: Optional[Callable[[int, int], None]] = None

    def _ensure_config(self):
        """Create a default config if none exists."""
        if not self.config_path.exists():
            default_config = {
                "interval_seconds": 3600,
                "repos": [
                    {
                        "name": "knowledge-cloud",
                        "url": "https://github.com/Str8biddness/synthesus-knowledge-cloud",
                        "target": "/home/dakin/Desktop/Synthesus_4.0/synthesus_framework/data/knowledge_cloud_mirror"
                    }
                ]
            }
            os.makedirs(self.config_path.parent, exist_ok=True)
            with open(self.config_path, "w") as f:
                json.dump(default_config, f, indent=2)

    def set_callback(self, callback: Callable[[int, int], None]):
        """Set callback for (status, timestamp)."""
        self._on_state_change = callback

    def trigger_sync(self):
        """Trigger a full sync cycle in a background thread."""
        if self._sync_thread and self._sync_thread.is_alive():
            logger.info("Mirror sync already in progress")
            return

        def _worker():
            logger.info("Mirror sync cycle started")
            if self._on_state_change:
                self._on_state_change(1, int(time.time())) # 1 = Syncing
            
            try:
                cfg = load_config(str(self.config_path))
                for repo in cfg.get("repos", []):
                    run_sync_command(repo)
                
                logger.info("Mirror sync cycle completed successfully")
                if self._on_state_change:
                    self._on_state_change(2, int(time.time())) # 2 = Synced
            except Exception as e:
                logger.error("Mirror sync cycle failed: %s", e)
                if self._on_state_change:
                    self._on_state_change(4, int(time.time())) # 4 = Error

        self._sync_thread = threading.Thread(target=_worker, daemon=True)
        self._sync_thread.start()

    def get_status(self) -> Dict[str, Any]:
        """Fetch current sync status (Mock for now, should read from mirror_sync.db)."""
        return {
            "last_sync_ts": int(time.time()),
            "status": "ready"
        }
