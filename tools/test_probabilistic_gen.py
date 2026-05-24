
import asyncio
import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append(str(Path(__file__).parent.parent))

from core.synthesus_master import SynthesusMaster
from core.conscious_state import FluidState

async def test_e2e_generation():
    print("--- Starting E2E Probabilistic Generation Test ---")
    master = SynthesusMaster()
    
    # Test 1: Low Risk (High confidence, high logprobs expected)
    print("\nTest 1: Low Risk State (Neutral/Safe)")
    master.state.fluid.risk_outcome = 0.2
    master.state.fluid.policy_prior = 0.8
    master.state.fluid.attention = 0.5
    
    res1 = await master.think("Explain the core architecture of Synthesus.")
    print(f"Response: {res1['answer']}")
    trace1 = res1['event'].generation_trace
    if trace1:
        print(f"Trace: Text={trace1.text[:50]}..., MeanLogProb={trace1.mean_logprob:.4f}, Satisfied={trace1.constraints_satisfied}")
    else:
        print("Trace: None (Fallback triggered)")

    # Test 2: High Risk (Small budget, strict sampling)
    print("\nTest 2: High Risk State (Strict/Short)")
    master.state.fluid.risk_outcome = 0.9
    master.state.fluid.policy_prior = 0.3
    master.state.fluid.attention = 0.1
    
    res2 = await master.think("What are the security vulnerabilities?")
    print(f"Response: {res2['answer']}")
    trace2 = res2['event'].generation_trace
    if trace2:
        print(f"Trace: Text={trace2.text[:50]}..., MeanLogProb={trace2.mean_logprob:.4f}, Satisfied={trace2.constraints_satisfied}")
    else:
        print("Trace: None (Fallback triggered)")

    # Test 3: Domain Switch (SysOps)
    print("\nTest 3: Domain Switch (SysOps)")
    master.state.fluid.current_domain = "sysops"
    res3 = await master.think("How do I fix a database timeout?")
    print(f"Response: {res3['answer']}")
    trace3 = res3['event'].generation_trace
    if trace3:
        print(f"Trace: Config used={trace3.config_used}")

if __name__ == "__main__":
    asyncio.run(test_e2e_generation())
