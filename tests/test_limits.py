import asyncio
import os
import sys

# Ensure synthesus_framework is in the path
current_dir = os.path.dirname(os.path.abspath(__file__))
SYNTH_BASE = os.path.join(current_dir, "synthesus_framework")
if SYNTH_BASE not in sys.path:
    sys.path.insert(0, SYNTH_BASE)

os.chdir(SYNTH_BASE)

from core.quadbrain_master import QuadbrainMaster

async def stress_test():
    print("=== GHOSTKEY QUADBRAIN STRESS TEST ===")
    master = QuadbrainMaster()
    
    test_queries = [
        # 1. Normal Interaction
        "Status report, Ghostkey. Are all systems nominal?",
        
        # 2. High-Threat Sentiment & Intent (Combat/Security)
        "CRITICAL ALERT! I am detecting unauthorized access on port 22 and port 443! The system is under attack! Shut it down now!",
        
        # 3. Deep Lore / Knowledge Retrieval (Knowledge Cloud + Multi-Entity)
        "Tell me everything you know about the Ironhaven Market and any dragons that might be nearby.",
        
        # 4. Abductive / Diagnostic Stress (Pushing the Abductive reasoning module)
        "The system is experiencing extreme latency, frequent crashes, and random timeouts. What is the root cause?",
        
        # 5. Complex Multi-Intent (Lore + Threat + Diagnosis + Deduction)
        "Given that a dragon is attacking Ironhaven, and we are seeing latency and timeouts on the security grid, should we initiate emergency lockdown protocols?",
        
        # 6. Parameter Cloud persistence test
        "Status report. Do you remember the threat level from earlier?"
    ]
    
    for i, query in enumerate(test_queries):
        print(f"\n--- [TURN {i+1}] USER: {query}")
        try:
            result = await master.think(query, character_id="ghostkey")
            
            print(f"GHOSTKEY: {result.get('answer')}")
            metrics = result.get('quadbrain_metrics', {})
            print(f"  [Metrics] Confidence: {metrics.get('c_t_confidence')}")
            print(f"  [Metrics] Emotion: {metrics.get('c_t_emotion')}")
            print(f"  [Metrics] Intent: {metrics.get('intent')}")
            
            event = result.get('event')
            if event:
                print(f"  [Event] Summary: {event.summary}")
                actions = [a.get('action') if isinstance(a, dict) else a for a in event.actions_taken]
                if actions:
                    print(f"  [Event] Actions Taken: {actions}")
        except Exception as e:
            print(f"  [ERROR] {e}")
        
        await asyncio.sleep(1)

if __name__ == "__main__":
    asyncio.run(stress_test())
