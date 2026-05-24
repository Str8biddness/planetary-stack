"""
AIVM — Synthesus AI Virtual Machine Infrastructure

Provides:
- Model loading/unloading with hot-swap support
- Instruction dispatcher for VM operations
- Resource allocation and tracking
- Concurrent model execution without conflicts
- Error recovery systems
- ONNX model integration hooks
"""

from __future__ import annotations

from model_loader import (
    ModelLoader,
    ModelRegistry,
    ModelState,
    ModelInfo,
    SandboxExecutor,
    ONNXModelWrapper,
    InferenceRequest,
    InferenceResult,
)

from execution_engine import (
    ExecutionEngine,
    InstructionDispatcher,
    ResourcePool,
    VMInstruction,
    InstructionResult,
    InstructionType,
    ResourceAllocation,
)

from orchestrator import (
    AIVMOrchestrator,
    AIVMStatus,
    AIVMConfig,
)

__all__ = [
    # Model loader
    "ModelLoader",
    "ModelRegistry",
    "ModelState",
    "ModelInfo",
    "SandboxExecutor",
    "ONNXModelWrapper",
    "InferenceRequest",
    "InferenceResult",
    # Execution engine
    "ExecutionEngine",
    "InstructionDispatcher",
    "ResourcePool",
    "VMInstruction",
    "InstructionResult",
    "InstructionType",
    "ResourceAllocation",
    # Orchestrator
    "AIVMOrchestrator",
    "AIVMStatus",
    "AIVMConfig",
]