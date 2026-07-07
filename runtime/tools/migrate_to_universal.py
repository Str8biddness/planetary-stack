#!/usr/bin/env python3
"""
Synthesus 2.0 — Universal Migration Script
AIVM LLC

Populates the Universal Parameter Layer (V2) with existing:
1. Character Bios, Personality, Knowledge, and Patterns.
2. Global patterns and n-gram groundings.
"""

import json
import logging
import os
import sys
from pathlib import Path

# Setup path
ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from core.universal_substrate import UniversalSubstrate

logging.basicConfig(level=logging.INFO, format="%(levelname)s | %(message)s")
log = logging.getLogger("migration")

def main():
    substrate = UniversalSubstrate()
    log.info("Starting Universal Migration...")

    # 1. Migrate Characters
    char_dir = ROOT / "characters"
    if char_dir.exists():
        for char_id in os.listdir(char_dir):
            path = char_dir / char_id
            if not path.is_dir():
                continue
                
            log.info(f"Migrating character: {char_id}")
            for f in os.listdir(path):
                if f.endswith(".json"):
                    attr = f.replace(".json", "")
                    with open(path / f, "r") as json_f:
                        try:
                            data = json.load(json_f)
                            # Store in right_hemisphere
                            substrate.set_parameter(
                                namespace=f"char_{char_id}.{attr}",
                                value=data,
                                domain="right_hemisphere"
                            )
                        except Exception as e:
                            log.error(f"Failed to migrate {char_id}/{f}: {e}")

    # 2. Migrate Global Patterns (Left Hemisphere)
    data_dir = ROOT / "data"
    patterns_file = data_dir / "patterns.json"
    if patterns_file.exists():
        log.info("Migrating global patterns to left_hemisphere...")
        with open(patterns_file, "r") as f:
            try:
                patterns = json.load(f)
                substrate.set_parameter(
                    namespace="patterns.global",
                    value=patterns,
                    domain="left_hemisphere"
                )
            except Exception as e:
                log.error(f"Failed to migrate global patterns: {e}")

    # 3. Handle Unified Stats
    # If the V2 stats exist, we mark them as 'left_hemisphere' compliant
    stats_path = data_dir / "parameter_cloud_v2_stats.json"
    if stats_path.exists():
        with open(stats_path, "r") as f:
            stats = json.load(f)
            stats["status"] = "active_hemisphere_split"
            stats["hemispheres"] = ["left", "right"]
        with open(stats_path, "w") as f:
            json.dump(stats, f, indent=2)

    log.info("Migration Complete!")

if __name__ == "__main__":
    main()
