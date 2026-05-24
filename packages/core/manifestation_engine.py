# core/manifestation_engine.py
"""
Manifestation Engine — "The Freezer"
AIVM Synthesus 4.0

Orchestrates the transition from a live development state to a bootable,
frozen hardware image (ISO). Handles kernel compilation, parameter hardening,
and filesystem manifestation.
"""

from __future__ import annotations

import asyncio
import logging
import os
import shutil
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, List, Optional

logger = logging.getLogger(__name__)

class ManifestationEngine:
    def __init__(self, framework_root: str | Path, iso_root: str | Path):
        self.framework_root = Path(framework_root)
        self.iso_root = Path(iso_root)
        self.manifest_dir = self.iso_root / "airootfs"
        self._is_freezing = False
        self._last_freeze_status = "idle"
        self._freeze_progress = 0

    async def freeze_system(self, volume_id: str = "SYNTHESUS_4.0") -> Dict[str, Any]:
        """
        Orchestrate the full system freeze process.
        """
        if self._is_freezing:
            return {"status": "already_freezing", "progress": self._freeze_progress}

        self._is_freezing = True
        self._freeze_progress = 0
        self._last_freeze_status = "starting"
        
        try:
            # 1. Sync Knowledge Cloud
            self._last_freeze_status = "syncing_knowledge_cloud"
            self._freeze_progress = 10
            await self._sync_knowledge()

            # 2. Compile Hardened Kernel
            self._last_freeze_status = "compiling_hardened_kernel"
            self._freeze_progress = 30
            await self._compile_kernel()

            # 3. Encrypt Enclave Parameters
            self._last_freeze_status = "hardening_parameters"
            self._freeze_progress = 60
            await self._harden_params()

            # 4. Manifest Filesystem
            self._last_freeze_status = "manifesting_filesystem"
            self._freeze_progress = 80
            await self._manifest_fs()

            # 5. Build Bootable ISO
            self._last_freeze_status = "generating_iso"
            self._freeze_progress = 90
            iso_path = await self._generate_iso(volume_id)

            self._is_freezing = False
            self._freeze_progress = 100
            self._last_freeze_status = "complete"
            
            return {
                "status": "complete",
                "iso_path": str(iso_path),
                "timestamp": time.time()
            }

        except Exception as e:
            logger.error(f"Freeze failed: {e}")
            self._is_freezing = False
            self._last_freeze_status = f"failed: {str(e)}"
            raise

    async def _sync_knowledge(self):
        # Already handled by Phase 1/4 integration, but we ensure persistence
        src = self.framework_root / "data" / "knowledge_cache"
        dest = self.manifest_dir / "opt" / "synthesus" / "knowledge"
        dest.mkdir(parents=True, exist_ok=True)
        if src.exists():
             # Use copytree with ignore if needed
             shutil.copytree(src, dest, dirs_exist_ok=True)

    async def _compile_kernel(self):
        build_dir = self.framework_root / "build"
        # Trigger cmake/make
        process = await asyncio.create_subprocess_exec(
            "make", "-j4",
            cwd=str(build_dir),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        
        # Move binaries to manifest
        bin_dest = self.manifest_dir / "usr" / "local" / "bin"
        bin_dest.mkdir(parents=True, exist_ok=True)
        shutil.copy(build_dir / "zo_kernel", bin_dest / "zo_kernel")
        shutil.copy(build_dir / "_synthesus_kernel.cpython-312-x86_64-linux-gnu.so", bin_dest / "_synthesus_kernel.so")

    async def _harden_params(self):
        # Mock parameter hardening: remove dev keys, set production flags
        config_dest = self.manifest_dir / "etc" / "synthesus"
        config_dest.mkdir(parents=True, exist_ok=True)
        with open(config_dest / "mode.json", "w") as f:
            import json
            json.dump({"mode": "production", "enclave_locked": True}, f)

    async def _manifest_fs(self):
        # Sync the framework code itself
        code_dest = self.manifest_dir / "opt" / "synthesus" / "framework"
        code_dest.mkdir(parents=True, exist_ok=True)
        # Copy src while excluding caches/git
        shutil.copytree(
            self.framework_root, 
            code_dest, 
            ignore=shutil.ignore_patterns("__pycache__", ".git", "build", "data"),
            dirs_exist_ok=True
        )
        
        # Ensure 'aivm' and 'packages' are present
        logger.info("Manifestation: Sycing AIVM packages to /opt/synthesus/framework/packages")

    async def _generate_iso(self, volume_id: str) -> Path:
        output_iso = Path.home() / f"{volume_id}_{int(time.time())}.iso"
        # Wrap genisoimage
        cmd = [
            "genisoimage",
            "-R", "-J",
            "-V", volume_id,
            "-o", str(output_iso),
            str(self.iso_root)
        ]
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        await process.communicate()
        return output_iso

    def get_status(self) -> Dict[str, Any]:
        return {
            "is_freezing": self._is_freezing,
            "status": self._last_freeze_status,
            "progress": self._freeze_progress
        }
