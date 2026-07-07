"""Tests for AIVM sandbox crash protection."""
import pytest
import time
from aivm.sandbox import ModelSandbox, SandboxConfig, SandboxManager, IsolationLevel


def test_sandbox_execute_timeout():
    """Test that sandbox execute enforces timeout."""
    config = SandboxConfig(timeout_seconds=1)
    sandbox = ModelSandbox("test-id", config, "test-model")
    sandbox.activate()
    
    def slow_fn():
        time.sleep(10)  # Will exceed 1s timeout
        return "done"
    
    result = sandbox.execute(slow_fn)
    assert result.error is not None
    assert "timed out" in result.error.lower()
    assert result.execution_time_ms < 2000  # Should be under 2s, not 10s


def test_sandbox_execute_normal():
    """Test normal sandbox execution."""
    config = SandboxConfig(timeout_seconds=5)
    sandbox = ModelSandbox("test-id", config, "test-model")
    sandbox.activate()
    
    def normal_fn(x):
        return x * 2
    
    result = sandbox.execute(normal_fn, 5)
    assert result.error is None
    assert result.output == 10


def test_sandbox_manager_crash_recovery():
    """Test SandboxManager handles None gracefully."""
    manager = SandboxManager()
    
    # Should not crash with missing model
    result = manager.execute_in_sandbox(lambda: "ok", "nonexistent-model", create_if_missing=False)
    assert result.error is not None
    assert "No sandbox" in result.error


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
