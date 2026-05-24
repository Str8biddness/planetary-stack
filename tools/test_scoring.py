#!/usr/bin/env python3
"""Quick test: verify off-script queries score below threshold, on-script score above."""
import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

import json
from api.fastapi_server import _match_pattern, MATCH_QUALITY_THRESHOLD

# Load patterns
with open(os.path.join(os.path.dirname(__file__), "..", "characters", "garen", "patterns.json")) as f:
    patterns = json.load(f)

on_script = [
    ("What do you sell?", True),
    ("I need a sword", True),
    ("Tell me about yourself", True),
    ("Got any work for me?", True),
    ("That's too much, give me a discount", True),
    ("How'd you get that scar?", True),
    ("Heard any rumors?", True),
    ("What do you think about the Duke?", True),
    ("How's business been?", True),
    ("Show me something special", True),
    ("Is it dangerous?", True),
    ("I'll take the job", True),
    ("Hello", True),
    ("Goodbye, old friend", True),
    ("Thank you, Garen", True),
    ("I brought back your caravan! The silk is safe", True),
]

off_script = [
    ("What would happen if dragons attacked the city?", False),
    ("Do you ever think about retiring?", False),
    ("I killed a man on the road. Do you judge me?", False),
    ("If you could change one thing about your life, what would it be?", False),
    ("I think someone in this town is a spy", False),
    ("What's your biggest regret?", False),
]

print(f"MATCH_QUALITY_THRESHOLD = {MATCH_QUALITY_THRESHOLD}")
print(f"\n{'='*80}")
print(f"{'ON-SCRIPT queries (should score >= threshold)':^80}")
print(f"{'='*80}")

on_pass = 0
on_fail = 0
for query, _ in on_script:
    match, score = _match_pattern(query, patterns)
    pid = match.get("id", "?") if match else "NONE"
    ok = score >= MATCH_QUALITY_THRESHOLD
    tag = "✓" if ok else "✗ FAIL"
    if ok:
        on_pass += 1
    else:
        on_fail += 1
    print(f"  {tag}  score={score:.3f}  pid={pid:<16} | {query}")

print(f"\n{'='*80}")
print(f"{'OFF-SCRIPT queries (should score < threshold)':^80}")
print(f"{'='*80}")

off_pass = 0
off_fail = 0
for query, _ in off_script:
    match, score = _match_pattern(query, patterns)
    pid = match.get("id", "?") if match else "NONE"
    ok = score < MATCH_QUALITY_THRESHOLD
    tag = "✓" if ok else "✗ FAIL"
    if ok:
        off_pass += 1
    else:
        off_fail += 1
    print(f"  {tag}  score={score:.3f}  pid={pid:<16} | {query}")

print(f"\n{'='*80}")
total = on_pass + off_pass
total_all = len(on_script) + len(off_script)
print(f"  ON-SCRIPT:  {on_pass}/{len(on_script)} correct")
print(f"  OFF-SCRIPT: {off_pass}/{len(off_script)} correct")
print(f"  TOTAL:      {total}/{total_all}")
if total == total_all:
    print(f"  ✓ ALL PASSED")
else:
    print(f"  ✗ {total_all - total} FAILURES")
