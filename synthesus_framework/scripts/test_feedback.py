import asyncio
from core.synthesus_master import SynthesusMaster
from core.conscious_state import NarrativeEvent

async def test_feedback():
    master = SynthesusMaster()
    
    # Manually create a narrative event with an abductive explanation
    event = NarrativeEvent(
        t=0,
        query="Why is it slow?",
        engines_used=["abductive"],
        summary="High CPU usage detected",
        role="investigator",
        emotional_tone="concerned",
        explanations=["Hypothesis for slowdown caused by high_cpu_usage (post=0.85, like=0.9)"]
    )
    master.state.narrative.timeline.append(event)
    
    # Record positive feedback
    print("Recording positive feedback for event 0...")
    await master.record_feedback(0, "correct")
    
    # Check if learned_rules in inductive module was updated
    rule_key = "high_cpu_usage=>slowdown"
    stats = master.core.inductive.learned_rules.get(rule_key)
    print(f"Stats for {rule_key}: {stats}")
    assert stats is not None
    assert stats["positive"] == 1
    
    # Record negative feedback
    print("Recording negative feedback for event 0...")
    await master.record_feedback(0, "not helpful")
    stats = master.core.inductive.learned_rules.get(rule_key)
    print(f"Stats for {rule_key} after negative: {stats}")
    assert stats["negative"] == 1

    print("Feedback wiring verification passed!")

if __name__ == "__main__":
    asyncio.run(test_feedback())
