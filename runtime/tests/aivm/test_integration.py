"""Integration tests for AIVM orchestrator with concurrent models."""
import pytest
import threading
import time
from core.aivm import AIVMOrchestrator
from core.aivm.execution_engine import InstructionType, VMInstruction
from core.aivm.inference_scheduler import InferencePriority, InferenceRequest
from core.aivm.sandbox import SandboxManager, SandboxConfig, ModelSandbox


def test_orchestrator_lifecycle():
    """Test basic orchestrator initialization and shutdown."""
    o = AIVMOrchestrator({"max_concurrent_inference": 2})
    assert o.initialize()
    assert o.get_full_status()["initialized"]
    o.shutdown()
    assert not o.get_full_status()["running"]


def test_dispatcher_works():
    """Test dispatcher processes instructions."""
    o = AIVMOrchestrator()
    o.initialize()

    results = []

    def handler(payload):
        results.append(payload["priority"])
        return {"success": True}

    o._dispatcher.register_handler(InstructionType.HEALTH_CHECK, handler)

    result = o._dispatcher.dispatch(VMInstruction(
        instruction_id="sync1",
        instruction_type=InstructionType.HEALTH_CHECK,
        payload={"priority": "normal"},
    ))

    assert result.success is True
    assert results == ["normal"]
    o.shutdown()


def test_sandbox_timeout_enforcement():
    """Test sandbox SIGALRM timeout is enforced."""
    config = SandboxConfig(timeout_seconds=1)
    sandbox = ModelSandbox("test-id", config, "test-model")
    sandbox.activate()
    
    def slow_fn():
        time.sleep(10)
        return "done"
    
    result = sandbox.execute(slow_fn)
    
    assert result.error is not None
    assert "timed out" in result.error.lower()
    assert result.execution_time_ms < 5000


def test_concurrent_inference_registration():
    """Test multiple models can register handlers concurrently."""
    o = AIVMOrchestrator({"max_concurrent_inference": 4})
    o.initialize()

    def handler(model_id):
        def _handler(input_data):
            return {"model": model_id, "result": "ok"}
        return _handler

    for i in range(3):
        o.register_model_handler(f"model_{i}", handler(f"model_{i}"))

    stats = o.get_full_status()
    assert len(stats["inference_scheduler"]["registered_models"]) == 3
    
    o.shutdown()


def test_resource_allocation_tracking():
    """Test memory allocation tracking in the orchestrator resource pool."""
    o = AIVMOrchestrator()
    o.initialize()

    allocation = o._resource_allocator.allocate_memory(
        "test_model",
        256 * 1024 * 1024,
    )
    assert allocation.granted is True
    assert o._resource_allocator.stats()["active_allocations"] == 1
    assert o._resource_allocator.release_memory(allocation.allocation_id) is True

    o.shutdown()


def test_circuit_breaker_rejects_on_open():
    """Test circuit breaker rejects requests when open."""
    from core.aivm.error_recovery import CircuitState
    
    o = AIVMOrchestrator()
    o.initialize()

    cb = o._error_recovery.get_circuit_breaker("dispatcher")
    assert cb.can_execute()

    cb._state = CircuitState.OPEN
    cb._failure_count = 10
    
    assert not cb.can_execute()
    
    o.shutdown()


def test_context_lifecycle():
    """Test context creation through termination."""
    o = AIVMOrchestrator()
    o.initialize()

    ctx_id = o.create_context("test_model", {"session": "data"})
    assert ctx_id is not None

    ctx = o._context_manager.get_context(ctx_id)
    assert ctx is not None
    assert ctx.model_id == "test_model"

    success = o._context_manager.initialize_context(ctx_id)
    assert success

    updated = o._context_manager.update_session_data(ctx_id, "key", "value")
    assert updated

    val = o._context_manager.get_session_data(ctx_id, "key")
    assert val == "value"

    terminated = o._context_manager.terminate_context(ctx_id)
    assert terminated
    
    o.shutdown()


def test_sandbox_manager_create():
    """Test sandbox manager creates sandboxes properly."""
    manager = SandboxManager()
    config = SandboxConfig(memory_limit_mb=256, timeout_seconds=5)
    
    sandbox_id = manager.create_sandbox("model1", config)
    assert sandbox_id is not None
    
    sandbox = manager.get_sandbox(model_id="model1")
    assert sandbox is not None
    assert sandbox.model_id == "model1"
    
    destroyed = manager.destroy_sandbox("model1")
    assert destroyed


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
