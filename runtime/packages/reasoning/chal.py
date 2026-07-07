"""Compatibility imports for canonical CHAL frame contracts.

The stable frame boundary lives in ``core.chal.frames``. This module remains so
legacy PPBRS and reasoning imports keep working while the runtime converges on
the shared CHAL package boundary.
"""

from __future__ import annotations

try:
    from core.chal.frames import (
        Checkpoint,
        CognitiveFrameCheckpoint,
        CognitiveFrameExecutionPlan,
        CognitiveFrameMessage,
        CognitiveFrameTask,
        CognitiveFrameTelemetry,
        CognitiveTask,
        ExecutionPlan,
        ModuleMessage,
        PPBRSFirmwareSignal,
        TelemetryRecord,
        build_ppbrs_firmware_signal,
    )
except ModuleNotFoundError:
    from chal.frames import (
        Checkpoint,
        CognitiveFrameCheckpoint,
        CognitiveFrameExecutionPlan,
        CognitiveFrameMessage,
        CognitiveFrameTask,
        CognitiveFrameTelemetry,
        CognitiveTask,
        ExecutionPlan,
        ModuleMessage,
        PPBRSFirmwareSignal,
        TelemetryRecord,
        build_ppbrs_firmware_signal,
    )


__all__ = [
    "Checkpoint",
    "CognitiveFrameCheckpoint",
    "CognitiveFrameExecutionPlan",
    "CognitiveFrameMessage",
    "CognitiveFrameTask",
    "CognitiveFrameTelemetry",
    "CognitiveTask",
    "ExecutionPlan",
    "ModuleMessage",
    "PPBRSFirmwareSignal",
    "TelemetryRecord",
    "build_ppbrs_firmware_signal",
]
