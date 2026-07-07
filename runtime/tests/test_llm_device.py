import pytest
from packages.core.chal.frames import CognitiveTask, TelemetryRecord
from packages.core.chal.devices.llm_device import LLMGenerationDevice

def test_llm_device_real_call():
    """Test a real call to the local Ollama LLM."""
    device = LLMGenerationDevice()
    task = CognitiveTask(
        task_id="t1", 
        query="Say the word 'Test'", 
        budgets={"latency_ms": 30000.0}
    )
    
    output, telemetry = device.generate(task)
    
    assert isinstance(output, str)
    assert len(output) > 0
    assert isinstance(telemetry, TelemetryRecord)
    assert telemetry.component == "llm_device"
    assert telemetry.latency_ms <= 30000.0
    assert telemetry.metadata["status"] == "success"

def test_llm_device_forced_timeout():
    """Test that violating budget_ms produces a structured error frame, not a string."""
    device = LLMGenerationDevice()
    # 1ms budget is physically impossible to meet over HTTP + LLM generation
    task = CognitiveTask(
        task_id="t2", 
        query="Explain quantum mechanics.", 
        budgets={"latency_ms": 1.0}
    )
    
    output, telemetry = device.generate(task)
    
    assert isinstance(output, dict)
    assert output["error"] == "TimeoutError"
    assert "budget" in output["message"]
    assert isinstance(telemetry, TelemetryRecord)
    assert telemetry.fallback_used is True
    assert telemetry.metadata["status"] == "timeout"
