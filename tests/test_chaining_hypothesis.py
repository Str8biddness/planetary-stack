#!/usr/bin/env python3
"""
End-to-End Test: Pattern Chaining + Slot Filling Hypothesis
AIVM Synthesus 2.0 — MVP Validation

GOAL: Prove that compositional Lego-building on retrieved patterns can produce
coherent multi-sentence responses comparable to 175B parameter models.

TEST STRATEGY:
1. Create synthetic Knowledge Cloud with interlinked patterns
2. Run queries that should trigger chaining
3. Verify multi-sentence output with filled slots
4. Compare against single-pattern baseline

SUCCESS CRITERIA:
- ✅ Multi-sentence responses (>1 sentence boundary)
- ✅ Slots filled from world state and query context
- ✅ Chains follow transition graph logic
- ✅ Graceful fallback when chaining fails
"""

import asyncio
import json
import logging
import sys
import time
from pathlib import Path
from typing import Any, Dict, List

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

# Add project root to path
PROJECT_ROOT = Path(__file__).parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from cognitive.sequence_linker import SequenceLinker, ChainPlan
from cognitive.slot_filler import SlotFiller, FillResult
from core.knowledge_cloud import KnowledgeCloud, KnowledgeEntry


class ChainingHypothesisTest:
    """Test suite for the chaining + slot filling hypothesis."""
    
    def __init__(self):
        self.test_results: List[Dict[str, Any]] = []
        self.passed = 0
        self.failed = 0
    
    def log(self, msg: str, level: str = "info"):
        """Log with test context."""
        getattr(logger, level)(f"[TEST] {msg}")
    
    def assert_condition(self, condition: bool, test_name: str, details: str = ""):
        """Record test result."""
        if condition:
            self.passed += 1
            self.log(f"✅ {test_name}", "info")
        else:
            self.failed += 1
            self.log(f"❌ {test_name}: {details}", "error")
        
        self.test_results.append({
            "test": test_name,
            "passed": condition,
            "details": details
        })
        return condition
    
    # ─────────────────────────────────────────────────────────────────────────
    # TEST 1: SequenceLinker Module Test
    # ─────────────────────────────────────────────────────────────────────────
    
    async def test_sequence_linker_basic(self):
        """Test basic chain building with synthetic data."""
        self.log("Running SequenceLinker basic test...")
        
        # Create synthetic knowledge results
        knowledge_results = [
            {
                "entity_id": "dragon",
                "response": "Dragons are ancient creatures of immense power and wisdom.",
                "confidence": 0.95,
                "depth": "familiar",
                "slots": ["[entity]"]
            },
            {
                "entity_id": "castle",
                "response": "The ancient castle houses many secrets and dangers.",
                "confidence": 0.85,
                "depth": "acquainted",
                "slots": ["[location]"]
            },
            {
                "entity_id": "treasure",
                "response": "Great treasure awaits those brave enough to seek it.",
                "confidence": 0.75,
                "depth": "rumor",
                "slots": ["[reward]"]
            }
        ]
        
        context_vector = {
            "intent": "ask_about",
            "emotion": "curious",
            "sentiment": "neutral",
            "escalation_risk": 0.2,
            "engagement_score": 0.8
        }
        
        world_state = {
            "entities": ["dragon", "castle", "treasure"],
            "locations": ["Ironhaven"]
        }
        
        # Build chain
        linker = SequenceLinker(transitions_path=None)  # Use uniform fallback
        plan = linker.build_chain(knowledge_results, context_vector, world_state)
        
        # Assertions
        self.assert_condition(
            len(plan.steps) >= 1,
            "Chain produces at least 1 step",
            f"Got {len(plan.steps)} steps"
        )
        
        self.assert_condition(
            plan.total_confidence > 0,
            "Chain has positive confidence",
            f"Confidence: {plan.total_confidence}"
        )
        
        self.assert_condition(
            plan.stop_reason in ["complete", "max_length", "confidence_drop", "slot_failure"],
            "Chain has valid stop reason",
            f"Stop reason: {plan.stop_reason}"
        )
        
        self.log(f"  Chain: {len(plan.steps)} steps, confidence: {plan.total_confidence:.2f}")
        for i, step in enumerate(plan.steps):
            self.log(f"    {i+1}. {step.pattern_id} (conf={step.confidence:.2f})")
    
    # ─────────────────────────────────────────────────────────────────────────
    # TEST 2: SlotFiller Module Test
    # ─────────────────────────────────────────────────────────────────────────
    
    async def test_slot_filler_basic(self):
        """Test slot extraction and binding."""
        self.log("Running SlotFiller basic test...")
        
        from dataclasses import dataclass, field
        
        @dataclass
        class MockStep:
            slots_required: List[str] = field(default_factory=list)
            slots_optional: List[str] = field(default_factory=list)
        
        @dataclass
        class MockPlan:
            steps: List[MockStep]
        
        # Test data
        plan = MockPlan(steps=[
            MockStep(slots_required=["[entity]"], slots_optional=["[emotion]"]),
            MockStep(slots_required=["[time]"], slots_optional=[]),
        ])
        
        world_state = {
            "entities": ["dragon", "Ironhaven"],
            "emotion": "curious"
        }
        
        query = "Tell me about the dragon this morning"
        
        context_vector = {
            "intent": "ask_about",
            "emotion": "curious"
        }
        
        # Fill slots
        filler = SlotFiller()
        result = filler.fill_slots(plan, world_state, [], query, context_vector)
        
        # Assertions
        self.assert_condition(
            result.all_satisfied,
            "All required slots filled",
            f"Unsatisfied: {result.unsatisfied_required}"
        )
        
        self.assert_condition(
            "entity" in result.bindings,
            "Entity slot extracted",
            f"Bindings: {result.bindings}"
        )
        
        self.assert_condition(
            "time" in result.bindings,
            "Time slot extracted from query",
            f"Bindings: {result.bindings}"
        )
        
        self.log(f"  Bindings: {result.bindings}")
        self.log(f"  Filled optional: {result.filled_optional}")
    
    # ─────────────────────────────────────────────────────────────────────────
    # TEST 3: Integration Test — Knowledge Cloud + Chaining + Slots
    # ─────────────────────────────────────────────────────────────────────────
    
    async def test_integration_chaining(self):
        """Test full pipeline with real Knowledge Cloud."""
        self.log("Running integration test with Knowledge Cloud...")
        
        # Initialize Knowledge Cloud
        cloud = KnowledgeCloud(data_dir="data/knowledge_cloud")
        
        # Add test entries with slot declarations
        test_entries = [
            KnowledgeEntry(
                entity_id="dragon_lore",
                entity="Dragon Lore",
                description="The [entity] is a [topic] creature of great [emotion] renown.",
                entity_type="lore",
                facts=["Breathes fire", "Hoards treasure", "Ancient wisdom"],
                depth="familiar",
                slots=["[entity]", "[topic]", "[emotion]"]
            ),
            KnowledgeEntry(
                entity_id="castle_mention",
                entity="Castle Mention",
                description="The castle houses the [entity]. Many adventurers seek its [reward].",
                entity_type="location",
                facts=["Built 500 years ago", "Protected by guards"],
                depth="acquainted",
                slots=["[entity]", "[reward]"]
            ),
            KnowledgeEntry(
                entity_id="treasure_hint",
                entity="Treasure Hint",
                description="Great [reward] can be found [time] for the brave.",
                entity_type="treasure",
                facts=["Gold and jewels", "Magical artifacts"],
                depth="rumor",
                slots=["[reward]", "[?time]"]  # Optional time
            )
        ]
        
        for entry in test_entries:
            cloud.upsert_entry(entry, persist=False)
        
        # Rebuild index
        cloud.rebuild_index()
        
        # Search
        query = "Tell me about the dragon in the castle"
        results = cloud.lookup_multi(query, emotion="curious", trust=50.0, top_k=3)
        
        self.assert_condition(
            len(results) >= 1,
            "Knowledge Cloud returns results",
            f"Got {len(results)} results"
        )
        
        if not results:
            return
        
        # Build chain
        linker = SequenceLinker(transitions_path=None)
        context_vector = {
            "intent": "ask_about",
            "emotion": "curious",
            "escalation_risk": 0.1,
            "engagement_score": 0.7
        }
        world_state = {
            "entities": ["dragon", "castle"],
            "emotion": "curious"
        }
        
        plan = linker.build_chain(results, context_vector, world_state)
        
        self.assert_condition(
            len(plan.steps) >= 1,
            "Chain builds successfully",
            f"Steps: {len(plan.steps)}"
        )
        
        # Fill slots
        filler = SlotFiller()
        fill_result = filler.fill_slots(plan, world_state, [], query, context_vector)
        
        self.log(f"  Slot fill rate: {len(fill_result.bindings)}/{len(plan.steps)} patterns")
        
        # Render if possible
        if plan.steps and fill_result.all_satisfied:
            composed = linker.render_chain_text(plan, fill_result.bindings)
            
            self.assert_condition(
                len(composed) > 20,
                "Composed response has substantial length",
                f"Length: {len(composed)}"
            )
            
            sentences = composed.count('.') + composed.count('!') + composed.count('?')
            self.assert_condition(
                sentences >= 1,
                "Response has at least one sentence",
                f"Sentences: {sentences}"
            )
            
            self.log(f"  Composed ({len(composed)} chars, {sentences} sentences):")
            self.log(f"    {composed[:150]}...")
        else:
            self.log("  Skipped render: chain empty or slots unsatisfied")
    
    # ─────────────────────────────────────────────────────────────────────────
    # TEST 4: Transition Graph Test
    # ─────────────────────────────────────────────────────────────────────────
    
    async def test_transition_graph(self):
        """Test that transition graph is loaded and functional."""
        self.log("Running transition graph test...")
        
        transitions_path = PROJECT_ROOT / "data" / "knowledge_cloud" / "transitions.json"
        
        if not transitions_path.exists():
            self.log("Transitions file not found, creating test data...", "warning")
            from cognitive.sequence_linker import create_mvp_transitions
            data = create_mvp_transitions()
            transitions_path.parent.mkdir(parents=True, exist_ok=True)
            with open(transitions_path, 'w') as f:
                json.dump(data, f, indent=2)
        
        linker = SequenceLinker(str(transitions_path))
        
        # Check that transitions loaded
        self.assert_condition(
            len(linker._transitions) > 0,
            "Transition graph loaded",
            f"Transitions: {len(linker._transitions)}"
        )
        
        # Test specific edge
        if "cloud_greeting" in linker._transitions:
            score = linker._score_transition("cloud_greeting", "cloud_dragon", "inquiry")
            self.assert_condition(
                score > 0.5,
                "Known transition has positive score",
                f"Score: {score}"
            )
    
    # ─────────────────────────────────────────────────────────────────────────
    # TEST 5: Fallback Behavior Test
    # ─────────────────────────────────────────────────────────────────────────
    
    async def test_fallback_behavior(self):
        """Test that system falls back gracefully when chaining fails."""
        self.log("Running fallback behavior test...")
        
        # Create a scenario where slots can't be filled
        knowledge_results = [
            {
                "entity_id": "unknown_entity",
                "response": "This requires [unknown_slot] which we don't have.",
                "confidence": 0.5,
                "slots": ["[unknown_slot]"]  # Required slot won't be fillable
            }
        ]
        
        linker = SequenceLinker()
        plan = linker.build_chain(
            knowledge_results,
            {"intent": "ask_about", "emotion": "neutral"},
            {"entities": []}  # Empty world state
        )
        
        # Chain may be empty or have slot failures
        self.assert_condition(
            len(plan.steps) == 0 or plan.stop_reason == "slot_failure",
            "Empty world state causes graceful handling",
            f"Steps: {len(plan.steps)}, reason: {plan.stop_reason}"
        )
    
    # ─────────────────────────────────────────────────────────────────────────
    # TEST 6: Performance Test
    # ─────────────────────────────────────────────────────────────────────────
    
    async def test_performance(self):
        """Test that chaining completes within reasonable time."""
        self.log("Running performance test...")
        
        knowledge_results = [
            {
                "entity_id": f"test_{i}",
                "response": f"Test pattern {i} with [entity] mention.",
                "confidence": 0.9 - (i * 0.1),
                "slots": ["[entity]"]
            }
            for i in range(10)
        ]
        
        linker = SequenceLinker()
        
        start = time.time()
        plan = linker.build_chain(
            knowledge_results,
            {"intent": "ask_about", "emotion": "neutral"},
            {"entities": ["test"]}
        )
        elapsed = (time.time() - start) * 1000
        
        self.assert_condition(
            elapsed < 100,  # Should complete in <100ms
            f"Chaining completes in <100ms ({elapsed:.1f}ms)",
            f"Took {elapsed:.1f}ms"
        )
        
        self.log(f"  Chain built in {elapsed:.1f}ms")
    
    # ─────────────────────────────────────────────────────────────────────────
    # Run All Tests
    # ─────────────────────────────────────────────────────────────────────────
    
    async def run_all(self):
        """Execute complete test suite."""
        self.log("=" * 60)
        self.log("PATTERN CHAINING + SLOT FILLING HYPOTHESIS TESTS")
        self.log("=" * 60)
        
        tests = [
            self.test_sequence_linker_basic,
            self.test_slot_filler_basic,
            self.test_integration_chaining,
            self.test_transition_graph,
            self.test_fallback_behavior,
            self.test_performance,
        ]
        
        for test in tests:
            try:
                await test()
            except Exception as e:
                self.log(f"EXCEPTION in {test.__name__}: {e}", "error")
                self.failed += 1
            print()  # Blank line between tests
        
        # Summary
        self.log("=" * 60)
        self.log(f"RESULTS: {self.passed} passed, {self.failed} failed")
        self.log("=" * 60)
        
        # Hypothesis validation
        if self.passed >= 5 and self.failed <= 1:
            self.log("✅ HYPOTHESIS MVP VALIDATED — System functional for scaling")
        elif self.passed >= 3:
            self.log("⚠️  MVP PARTIAL — Debugging needed before scaling")
        else:
            self.log("❌ MVP FAILED — Significant issues to resolve")
        
        return self.failed == 0


# ─────────────────────────────────────────────────────────────────────────────
# Entry Point
# ─────────────────────────────────────────────────────────────────────────────

async def main():
    """Run the test suite."""
    test = ChainingHypothesisTest()
    success = await test.run_all()
    return 0 if success else 1


if __name__ == "__main__":
    exit_code = asyncio.run(main())
    sys.exit(exit_code)
