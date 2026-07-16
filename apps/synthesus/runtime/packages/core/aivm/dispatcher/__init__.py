"""
AIVM Instruction Dispatcher
Routes VM instructions to appropriate handlers with priority queuing.
"""
from typing import Dict, Any, Optional, Callable, List
from dataclasses import dataclass, field
from enum import Enum
from collections import defaultdict
import threading
import time
import uuid
import logging

logger = logging.getLogger(__name__)


class InstructionType(Enum):
    """
    Enum defining the supported instruction types for the dispatcher.
    """
    LOAD_MODEL = "load_model"
    UNLOAD_MODEL = "unload_model"
    RUN_INFERENCE = "run_inference"
    HOTSWAP_MODEL = "hotswap_model"
    ALLOCATE_RESOURCE = "allocate_resource"
    DEALLOCATE_RESOURCE = "deallocate_resource"
    EXECUTE_CONTEXT = "execute_context"
    SYNC_STATE = "sync_state"
    HEALTH_CHECK = "health_check"


class Priority(Enum):
    """
    Enum defining instruction priority levels.
    """
    CRITICAL = 0
    HIGH = 1
    NORMAL = 2
    LOW = 3


@dataclass
class Instruction:
    """
    Represents an instruction packet to be dispatched.

    Attributes:
        id: Unique identifier for the instruction.
        type: The type of instruction.
        payload: Parameters for the instruction handler.
        priority: Priority level of the instruction.
        created_at: Timestamp when the instruction was created.
        deadline: Optional timestamp by which the instruction must be completed.
        model_id: Optional ID of the model this instruction pertains to.
        correlation_id: Optional ID for correlating related instructions.
    """
    id: str
    type: InstructionType
    payload: Dict[str, Any]
    priority: Priority = Priority.NORMAL
    created_at: float = field(default_factory=time.time)
    deadline: Optional[float] = None
    model_id: Optional[str] = None
    correlation_id: Optional[str] = None

    def __lt__(self, other):
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.created_at < other.created_at


class InstructionDispatcher:
    """
    Central dispatcher for AIVM instructions.
    Routes instructions to handlers based on type with priority queuing.
    """

    def __init__(self, max_workers: int = 4):
        self._handlers: Dict[InstructionType, List[Callable]] = defaultdict(list)
        self._queues: Dict[Priority, List[Instruction]] = {
            Priority.CRITICAL: [],
            Priority.HIGH: [],
            Priority.NORMAL: [],
            Priority.LOW: [],
        }
        self._active_instructions: Dict[str, Instruction] = {}
        self._completed: List[Dict[str, Any]] = []
        self._lock = threading.RLock()
        self._max_workers = max_workers
        self._running = False
        self._worker_threads: List[threading.Thread] = []
        self._results: Dict[str, Any] = {}
        self._error_handlers: Dict[InstructionType, List[Callable]] = defaultdict(list)

    def register_handler(self, instruction_type: InstructionType, handler: Callable):
        """
        Registers a handler for a specific instruction type.

        Args:
            instruction_type: The type of instruction this handler processes.
            handler: A callable that takes an Instruction and returns a result.
        """
        self._handlers[instruction_type].append(handler)
        logger.info(f"Registered handler for {instruction_type.value}")

    def register_error_handler(self, instruction_type: InstructionType, handler: Callable):
        """
        Registers an error handler for a specific instruction type.

        Args:
            instruction_type: The type of instruction to handle errors for.
            handler: A callable that takes (Instruction, Exception).
        """
        self._error_handlers[instruction_type].append(handler)

    def dispatch(self, instruction: Instruction) -> str:
        """
        Dispatches an instruction for asynchronous execution.

        Args:
            instruction: The Instruction object to dispatch.

        Returns:
            str: The unique ID of the dispatched instruction.
        """
        with self._lock:
            self._queues[instruction.priority].append(instruction)
            self._active_instructions[instruction.id] = instruction
        logger.debug(f"Dispatched instruction {instruction.id} of type {instruction.type.value}")
        return instruction.id

    def dispatch_now(self, instruction: Instruction) -> Any:
        """
        Executes an instruction immediately in the caller's thread.

        Args:
            instruction: The Instruction object to execute.

        Returns:
            Any: The result from the instruction handler.
        """
        return self._execute_instruction(instruction)

    def _execute_instruction(self, instruction: Instruction) -> Any:
        """Execute a single instruction."""
        handlers = self._handlers.get(instruction.type, [])
        if not handlers:
            error = f"No handler registered for {instruction.type.value}"
            logger.error(error)
            self._record_completion(instruction.id, error=error)
            return {"error": error}

        try:
            result = None
            for handler in handlers:
                result = handler(instruction)
            self._record_completion(instruction.id, result=result)
            return result
        except Exception as e:
            logger.error(f"Instruction {instruction.id} failed: {e}")
            for err_handler in self._error_handlers.get(instruction.type, []):
                try:
                    err_handler(instruction, e)
                except Exception as eh_err:
                    logger.error(f"Error handler failed: {eh_err}")
            self._record_completion(instruction.id, error=str(e))
            return {"error": str(e)}

    def _record_completion(self, instruction_id: str, result: Any = None, error: str = None):
        """Record instruction completion."""
        with self._lock:
            if instruction_id in self._active_instructions:
                del self._active_instructions[instruction_id]
            self._completed.append({
                "id": instruction_id,
                "result": result,
                "error": error,
                "completed_at": time.time(),
            })
            if len(self._completed) > 1000:
                self._completed = self._completed[-500:]

    def get_result(self, instruction_id: str, timeout: float = 30.0) -> Optional[Dict[str, Any]]:
        """
        Waits for and retrieves the result of a dispatched instruction.

        Args:
            instruction_id: The ID of the instruction to wait for.
            timeout: Maximum time to wait in seconds.

        Returns:
            Optional[Dict[str, Any]]: The completion record or None if timed out.
        """
        start = time.time()
        while time.time() - start < timeout:
            with self._lock:
                for record in reversed(self._completed):
                    if record["id"] == instruction_id:
                        return record
            time.sleep(0.01)
        return None

    def start_workers(self):
        """
        Starts the background worker threads for processing the instruction queue.
        """
        self._running = True
        for i in range(self._max_workers):
            t = threading.Thread(target=self._worker_loop, name=f"dispatcher-worker-{i}")
            t.daemon = True
            t.start()
            self._worker_threads.append(t)
        logger.info(f"Started {self._max_workers} dispatcher workers")

    def stop_workers(self):
        """
        Gracefully stops all background worker threads.
        """
        self._running = False
        for t in self._worker_threads:
            t.join(timeout=2.0)
        self._worker_threads.clear()
        logger.info("Stopped dispatcher workers")

    def _worker_loop(self):
        """Main worker loop with crash protection."""
        while self._running:
            try:
                instruction = self._get_next_instruction()
                if instruction:
                    self._execute_instruction(instruction)
                else:
                    time.sleep(0.05)  # Sleep when idle to prevent CPU spinning
            except Exception as e:
                logger.error(f"Worker loop error: {e}")
                time.sleep(1)  # Back off on error
                continue

    def _get_next_instruction(self) -> Optional[Instruction]:
        """Get the next instruction from queues by priority."""
        with self._lock:
            for priority in Priority:
                queue = self._queues[priority]
                if queue:
                    return queue.pop(0)
        return None

    def get_status(self) -> Dict[str, Any]:
        """
        Returns the current status of the dispatcher and its queues.

        Returns:
            Dict[str, Any]: A dictionary containing operational metrics.
        """
        with self._lock:
            return {
                "running": self._running,
                "workers": self._max_workers,
                "active_instructions": len(self._active_instructions),
                "queued": {p.value: len(self._queues[p]) for p in Priority},
                "completed_recent": len(self._completed),
                "registered_types": list(self._handlers.keys()),
            }
