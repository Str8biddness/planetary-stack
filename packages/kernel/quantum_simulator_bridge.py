"""
Python bridge for VirtualQuantumDevice requests.

The C++ VQD is intentionally simulator-agnostic. This module provides the
process-local callback that pybind11 can install with
VirtualQuantumDevice.set_executor(), then delegates gate execution to the
quantum simulator checkout at /home/dakin/Desktop/quantum-computing-system.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path
from typing import Any, Dict

logger = logging.getLogger(__name__)


QUANTUM_SYSTEM_ROOT = Path("/home/dakin/Desktop/quantum-computing-system")
QUANTUM_SYSTEM_SRC = QUANTUM_SYSTEM_ROOT / "src"

STATUS_DONE = 3
STATUS_ERROR = 4
ERROR_NONE = 0
ERROR_INVALID_GATE = 3
ERROR_EXECUTOR_FAILURE = 4

GATE_H = 1
GATE_X = 2
GATE_Y = 3
GATE_Z = 4
GATE_S = 5
GATE_T = 6
GATE_CNOT = 7
GATE_MEASURE = 8
GATE_RESET = 9


class QuantumSimulatorBridge:
    """Callable adapter from VQD request dictionaries to simulator results."""

    def __init__(self, simulator_src: str | Path = QUANTUM_SYSTEM_SRC) -> None:
        self.simulator_src = Path(simulator_src)
        if str(self.simulator_src) not in sys.path:
            sys.path.insert(0, str(self.simulator_src))

        from quantum_simulator.circuit import QuantumCircuit
        from quantum_simulator.gates import CNOT, Hadamard, Phase, TGate, PauliX, PauliY, PauliZ

        self._circuit_cls = QuantumCircuit
        self._gate_by_opcode = {
            GATE_H: Hadamard(),
            GATE_X: PauliX(),
            GATE_Y: PauliY(),
            GATE_Z: PauliZ(),
            GATE_S: Phase(),
            GATE_T: TGate(),
            GATE_CNOT: CNOT(),
        }

    def execute(self, request: Dict[str, Any]) -> Dict[str, int]:
        """Run one VQD gate request and return the C++ result contract."""
        try:
            opcode = int(request.get("gate_opcode", 0))
            qubit_count = int(request.get("qubit_count", 1))
            target = int(request.get("target_qubit", 0))
            control = int(request.get("control_qubit", 0))
            shots = max(1, int(request.get("shots", 1)))

            circuit = self._circuit_cls(qubit_count, name="synthesus_vqd_request")
            if opcode == GATE_RESET:
                return self._result(0)
            if opcode == GATE_MEASURE:
                counts = circuit.measure_all(shots=shots)
                return self._result(self._dominant_bitstring_as_int(counts))

            gate = self._gate_by_opcode.get(opcode)
            if gate is None:
                return self._error(ERROR_INVALID_GATE)

            if opcode == GATE_CNOT:
                circuit.add_gate(gate, control, target)
            else:
                circuit.add_gate(gate, target)

            counts = circuit.measure_all(shots=shots)
            return self._result(self._dominant_bitstring_as_int(counts))
        except Exception as exc:
            logger.exception("VirtualQuantumDevice simulator bridge failed: %s", exc)
            return self._error(ERROR_EXECUTOR_FAILURE)

    @staticmethod
    def _dominant_bitstring_as_int(counts: Dict[str, int]) -> int:
        if not counts:
            return 0
        bitstring, _ = max(counts.items(), key=lambda item: item[1])
        return int(bitstring, 2)

    @staticmethod
    def _result(value: int) -> Dict[str, int]:
        return {
            "status": STATUS_DONE,
            "result": int(value),
            "error_code": ERROR_NONE,
        }

    @staticmethod
    def _error(error_code: int) -> Dict[str, int]:
        return {
            "status": STATUS_ERROR,
            "result": 0,
            "error_code": int(error_code),
        }

    def attach(self, device: Any) -> Any:
        device.set_executor(self.execute)
        device._quantum_simulator_bridge = self
        return device


def create_bridged_quantum_device(*, simulator_src: str | Path = QUANTUM_SYSTEM_SRC) -> Any:
    """Create a pybind11 VirtualQuantumDevice with the Python simulator attached."""
    try:
        import _synthesus_kernel as native_kernel  # type: ignore
    except ImportError:
        import synthesus_kernel as native_kernel  # type: ignore

    bridge = QuantumSimulatorBridge(simulator_src=simulator_src)
    return bridge.attach(native_kernel.VirtualQuantumDevice())
