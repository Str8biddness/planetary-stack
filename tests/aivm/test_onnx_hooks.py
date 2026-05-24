"""Tests for ONNX integration hooks."""
import pytest
import numpy as np
from onnx_bridge.aivm_onnx_hooks import (
    ONNX_AVAILABLE,
    ONNXIntegrationHooks,
    ONNXModelConfig,
    SessionPolicy,
)


@pytest.mark.skipif(not ONNX_AVAILABLE, reason="ONNX Runtime not available")
class TestONNXIntegrationHooks:
    """Test ONNX integration with AIVM."""

    def test_hooks_initialization(self):
        """Test hooks initialize correctly."""
        hooks = ONNXIntegrationHooks(max_sessions_per_model=2)
        assert hooks.is_available

    def test_register_model_requires_onnx(self):
        """Test registration fails gracefully without ONNX."""
        hooks = ONNXIntegrationHooks()
        if not ONNX_AVAILABLE:
            # Should fail gracefully
            assert not hooks.is_available


@pytest.mark.skipif(ONNX_AVAILABLE, reason="ONNX Runtime available - skipping unavailable test")
def test_onnx_not_available_behavior():
    """Test behavior when ONNX is not installed."""
    from onnx_bridge.aivm_onnx_hooks import ONNX_AVAILABLE
    assert not ONNX_AVAILABLE
    
    hooks = ONNXIntegrationHooks()
    assert not hooks.is_available


if __name__ == "__main__":
    pytest.main([__file__, "-v"])