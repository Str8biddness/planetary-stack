#!/usr/bin/env python3
"""Quick test to verify Knowledge Cloud + SequenceLinker + SlotFiller integration."""

import sys
sys.path.insert(0, '.')

from core.knowledge_cloud import KnowledgeCloud
from cognitive.sequence_linker import SequenceLinker
from cognitive.slot_filler import SlotFiller

# Load the cloud
print("Loading Knowledge Cloud...")
cloud = KnowledgeCloud('data/knowledge_cloud')
print(f"Loaded {len(cloud._entries)} entries")

# Check slot entries
print("\nEntries with slots:")
for eid, entry in cloud._entries.items():
    if entry.slots:
        print(f"  {eid}: slots={entry.slots}")

# Test lookup
print("\nTesting lookup_multi...")
results = cloud.lookup_multi('Tell me about the dragon', emotion='curious', trust=50.0, top_k=3)
print(f"Found {len(results)} results:")
for r in results:
    print(f"  {r['entity_id']}: slots={r.get('slots', [])}")

# Test SequenceLinker
print("\nTesting SequenceLinker...")
linker = SequenceLinker()
plan = linker.build_chain(
    results,
    context_vector={'intent': 'ask_about', 'emotion': 'curious'},
    world_state={'entities': ['dragon', 'castle']}
)
print(f"Chain: {len(plan.steps)} steps, stop_reason={plan.stop_reason}")
for i, step in enumerate(plan.steps):
    print(f"  Step {i+1}: {step.pattern_id} (conf={step.confidence:.2f})")

# Test SlotFiller  
print("\nTesting SlotFiller...")
filler = SlotFiller()
fill_result = filler.fill_slots(
    chain_plan=plan,
    world_state={'entities': ['dragon', 'castle'], 'emotion': 'curious'},
    dialogue_memory=[],
    query='Tell me about the dragon this morning',
    context_vector={'intent': 'ask_about', 'emotion': 'curious'}
)
print(f"Fill result: satisfied={fill_result.all_satisfied}")
print(f"Bindings: {fill_result.bindings}")

if plan.steps and fill_result.all_satisfied:
    print("\nRendering chain...")
    composed = linker.render_chain_text(plan, fill_result.bindings)
    print(f"Composed response: {composed}")
    print("\n✅ Integration test PASSED - chaining and slot filling work!")
else:
    print("\n⚠️  Could not render - chain empty or slots not filled")
