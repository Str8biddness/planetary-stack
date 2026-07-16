#!/usr/bin/env python3
"""
Synthesus AIOS — Boot Entry Point (GUEST MODE)
AIVM LLC - Production Hardened Image

Launches the bounded NPC environment. 
Agentic tools and manifestation engines are DISABLED.
"""

import asyncio
import logging
import sys
from pathlib import Path

# Absolute Pathing for Monorepo (Assuming /opt/synthesus/framework in ISO)
ROOT = Path("/opt/synthesus/framework")
if not ROOT.exists():
    ROOT = Path(__file__).resolve().parent.parent

sys.path.insert(0, str(ROOT / "packages"))
sys.path.insert(0, str(ROOT / "packages" / "core"))
sys.path.insert(0, str(ROOT / "packages" / "knowledge"))
sys.path.insert(0, str(ROOT / "packages" / "reasoning"))
sys.path.insert(0, str(ROOT / "packages" / "kernel"))
sys.path.insert(0, str(ROOT / "packages" / "aivm"))

from core.synth_runtime import SynthRuntime

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("synthesus.aios.boot")

async def boot_aios():
    logger.info("Starting Synthesus AIOS in GUEST MODE...")
    
    # Initialize Bounded Runtime
    runtime = SynthRuntime(
        data_dir="/var/lib/synthesus/data",
        characters_dir="/var/lib/synthesus/characters",
        guest_mode=True
    )
    
    # Load all NPCs into the AIVM Kernel
    characters = runtime.list_characters()
    logger.info(f"Populating Kernel with {len(characters)} character(s)...")
    for char_id in characters:
        runtime.load_character(char_id)
        
    logger.info("AIOS GUEST KERNEL OPERATIONAL.")
    logger.info("AIVM Kernel is mediating all cognitive ticks.")
    logger.info("Agentic tools (Shell, Scraper, Freezer) are LOCKED.")

    # Keep alive
    try:
        while True:
            await asyncio.sleep(3600)
    except KeyboardInterrupt:
        logger.info("AIOS shutting down...")

if __name__ == "__main__":
    asyncio.run(boot_aios())
