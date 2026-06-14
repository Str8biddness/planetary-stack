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

    def check_for_action(self, query_vec, query_text):
        """
        Scans for constructive interference with command peaks.
        """
        best_resonance = 0.0
        triggered_action = None

        # Check every word in the query for action resonance
        words = query_text.lower().split()
        for word in words:
            w_vec = self.engine.word_to_vector(word)
            for name, data in self.action_anchors.items():
                res = self._calculate_resonance(w_vec, data['vec'])
                
                # Action Trigger Threshold: 0.99 for precise command resonance
                if res > 0.99:
                    if res > best_resonance:
                        best_resonance = res
                        triggered_action = data

        if triggered_action:
            print(f"⚡ [MOTOR] Resonance peak ({best_resonance:.4f}) detected for action: '{triggered_action['cmd']}'")
            return self._execute_action(triggered_action, query_text)
        
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
