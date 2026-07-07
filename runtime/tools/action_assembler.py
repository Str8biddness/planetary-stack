#!/usr/bin/env python3
"""
Action Assembler — Synthesus 5 Phase 17
Bridges 5-axis resonance peaks to physical system actions.
Uses the 'Action Shard' to trigger Linux commands via geometric alignment.
"""

import os
import sys
import json
import subprocess
from pathlib import Path

# Add tools directory to path
sys.path.append(os.path.abspath(os.path.dirname(__file__)))
from geometric_refinery import GeometricEngineFallback

class ActionAssembler:
    def __init__(self, engine):
        self.engine = engine
        self.shard_dir = Path("/home/dakin/dev/Synthesus_4.0/data/geometric_shards")
        # The 'Motor Cortex' of the system - Targeted for high-resonance matching
        self.action_anchors = {
            "list": {"vec": self.engine.word_to_vector("list"), "cmd": "ls -lh"},
            "who": {"vec": self.engine.word_to_vector("who"), "cmd": "whoami"}
        }

    # Explicit trigger keywords per action. Command execution must NOT be gated
    # on geometric resonance: in the 5-axis hash space cosine is inflated (random
    # words score ~0.99), so resonance-gating fired `whoami` on "tell me about
    # space". A motor that runs shell commands needs a deterministic, explicit
    # trigger — the literal intent word must appear in the query.
    TRIGGERS = {"list": {"list", "ls"}, "who": {"who", "whoami"}}

    def detect_action(self, query_text):
        """Return the matched action (or None) WITHOUT executing it."""
        words = {w.strip(".,;:!?") for w in query_text.lower().split()}
        for name, data in self.action_anchors.items():
            if words & self.TRIGGERS.get(name, {name}):
                return data
        return None

    def check_for_action(self, query_vec, query_text):
        action = self.detect_action(query_text)
        if action:
            print(f"⚡ [MOTOR] Explicit trigger detected for action: '{action['cmd']}'")
            return self._execute_action(action, query_text)
        return None

    def _execute_action(self, action, query_text):
        cmd = action['cmd']
        args = ""
        if "shards" in query_text.lower():
            args = "/home/dakin/dev/Synthesus_4.0/data/geometric_shards"
        
        full_cmd = f"{cmd} {args}".strip()
        print(f"🛠️  [SYSTEM] Physical instruction: {full_cmd}")
        
        try:
            result = subprocess.check_output(full_cmd, shell=True, text=True)
            return f"Action complete. Result:\n{result[:500]}"
        except Exception as e:
            return f"Action failed: {e}"

    def _calculate_resonance(self, v1, v2):
        dot = sum(a*b for a, b in zip(v1, v2))
        mag1 = sum(a*a for a in v1)**0.5
        mag2 = sum(a*a for a in v2)**0.5
        return dot / (mag1 * mag2) if (mag1 * mag2) > 0 else 0

if __name__ == "__main__":
    pass
