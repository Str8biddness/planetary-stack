import pytest
import sys
from pathlib import Path

# Add monorepo packages to path
PROJ_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(PROJ_ROOT / "packages"))

from aivm.kernel.core import AIVMKernel
from aivm.kernel.types import PersonaIdentity, SchedulerClass

@pytest.mark.asyncio
async def test_canonical_12_step_sequence():
    """
    Verifies that the AIVMKernel correctly executes and audits 
    the 12-step sequence defined in AIVM NPC Contract §5.
    """
    kernel = AIVMKernel()
    identity = PersonaIdentity(id="test_npc", name="Test NPC", archetype="villager")
    
    # Register NPC
    npc = kernel.spawn_npc(identity, scheduler=SchedulerClass.REALTIME_SUPPORTING)
    
    # Execute Tick
    await kernel.tick("test_npc", {"input": "hello"})
    
    # Verify Audit Trace
    # (Ignoring the 'spawn' event)
    audit_steps = [entry.step for entry in npc.audit_stream if entry.step != "spawn"]
    
    expected_sequence = [
        "admission", "perception", "plan", "route", "knowledge",
        "recall", "coherence_pre", "generate", "coherence_post",
        "memory_write", "emit", "close"
    ]
    
    assert audit_steps == expected_sequence, f"Trace mismatch! Got: {audit_steps}"
