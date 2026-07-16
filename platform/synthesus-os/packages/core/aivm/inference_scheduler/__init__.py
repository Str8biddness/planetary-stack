"""
AIVM Inference Scheduler
Schedules and manages inference requests across multiple models.
"""
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import uuid
import logging
from collections import defaultdict

logger = logging.getLogger(__name__)


class InferencePriority(Enum):
    INTERRUPT = 0
    CRITICAL = 1
    HIGH = 2
    NORMAL = 3
    BATCH = 4


@dataclass
class InferenceRequest:
    request_id: str
    model_id: str
    input_data: Dict[str, Any]
    priority: InferencePriority = InferencePriority.NORMAL
    created_at: float = field(default_factory=time.time)
    timeout_seconds: float = 30.0
    callback: Optional[Callable] = None
    metadata: Dict[str, Any] = field(default_factory=dict)

    def __lt__(self, other):
        if self.priority.value != other.priority.value:
            return self.priority.value < other.priority.value
        return self.created_at < other.created_at


@dataclass
class InferenceResult:
    request_id: str
    model_id: str
    output: Any
    error: Optional[str] = None
    execution_time_ms: float = 0.0
    queued_time_ms: float = 0.0
    completed_at: float = field(default_factory=time.time)


class InferenceScheduler:
    """
    Schedules inference requests across multiple models with priority queuing.
    Supports batching, backpressure, and concurrent model execution.
    """

    def __init__(self, max_concurrent_per_model: int = 4, max_queue_size: int = 1000):
        self._queues: Dict[str, List[InferenceRequest]] = defaultdict(list)
        self._running: Dict[str, int] = defaultdict(int)
        self._max_concurrent_per_model = max_concurrent_per_model
        self._max_queue_size = max_queue_size
        self._results: Dict[str, InferenceResult] = {}
        self._lock = threading.RLock()
        self._running_flag = False
        self._scheduler_thread: Optional[threading.Thread] = None
        self._model_handlers: Dict[str, Callable] = {}
        self._pending_requests: Dict[str, InferenceRequest] = {}
        self._completed_requests: List[Dict[str, Any]] = []
        self._metrics: Dict[str, Any] = {
            "total_requests": 0,
            "completed_requests": 0,
            "failed_requests": 0,
            "total_queue_time_ms": 0.0,
            "total_execution_time_ms": 0.0,
        }

    def register_model(self, model_id: str, handler: Callable):
        """Register an inference handler for a model."""
        self._model_handlers[model_id] = handler
        logger.info(f"Registered inference handler for model: {model_id}")

    def submit(self, request: InferenceRequest) -> str:
        """Submit an inference request."""
        with self._lock:
            if request.model_id not in self._queues:
                self._queues[request.model_id] = []

            if len(self._queues[request.model_id]) >= self._max_queue_size:
                logger.warning(f"Queue full for model {request.model_id}")
                return ""

            self._queues[request.model_id].append(request)
            self._pending_requests[request.request_id] = request
            self._metrics["total_requests"] += 1

        logger.debug(f"Submitted inference request {request.request_id} for model {request.model_id}")
        return request.request_id

    def submit_and_wait(self, request: InferenceRequest) -> InferenceResult:
        """Submit a request and wait for the result."""
        request_id = self.submit(request)
        if not request_id:
            return InferenceResult(
                request_id="",
                model_id=request.model_id,
                output=None,
                error="Queue full"
            )

        start_wait = time.time()
        while time.time() - start_wait < request.timeout_seconds:
            result = self.get_result(request_id)
            if result:
                return result
            time.sleep(0.01)

        return InferenceResult(
            request_id=request_id,
            model_id=request.model_id,
            output=None,
            error="Timeout waiting for result"
        )

    def get_result(self, request_id: str) -> Optional[InferenceResult]:
        """Get the result of a completed request."""
        return self._results.get(request_id)

    def cancel(self, request_id: str) -> bool:
        """Cancel a pending request."""
        with self._lock:
            if request_id in self._pending_requests:
                request = self._pending_requests[request_id]
                if request.model_id in self._queues:
                    try:
                        self._queues[request.model_id].remove(request)
                    except ValueError:
                        pass
                del self._pending_requests[request_id]
                return True
        return False

    def start(self):
        """Start the scheduler background thread."""
        self._running_flag = True
        self._scheduler_thread = threading.Thread(target=self._scheduler_loop, name="inference-scheduler")
        self._scheduler_thread.daemon = True
        self._scheduler_thread.start()
        logger.info("Inference scheduler started")

    def stop(self):
        """Stop the scheduler."""
        self._running_flag = False
        if self._scheduler_thread:
            self._scheduler_thread.join(timeout=5.0)
        logger.info("Inference scheduler stopped")

    def _scheduler_loop(self):
        """Main scheduler loop with crash protection and backpressure."""
        while self._running_flag:
            try:
                self._process_queues()
                # Dynamic sleep to prevent CPU spinning while remaining responsive
                # If queue is empty, sleep longer. If busy, sleep shorter.
                total_queued = sum(len(q) for q in self._queues.values())
                sleep_time = 0.1 if total_queued == 0 else 0.001
                time.sleep(sleep_time)
            except Exception as e:
                logger.error(f"Scheduler loop error: {e}")
                time.sleep(1)  # Back off on error to prevent crash loops
                continue

    def _process_queues(self):
        """Process all model queues."""
        with self._lock:
            for model_id in list(self._queues.keys()):
                self._process_model_queue(model_id)

    def _process_model_queue(self, model_id: str):
        """Process the queue for a specific model."""
        if self._running.get(model_id, 0) >= self._max_concurrent_per_model:
            return

        if model_id not in self._model_handlers:
            logger.warning(f"No handler registered for model {model_id}")
            return

        with self._lock:
            if not self._queues[model_id]:
                return
            request = self._queues[model_id].pop(0)

        self._running[model_id] = self._running.get(model_id, 0) + 1
        threading.Thread(
            target=self._execute_request,
            args=(request,),
            name=f"inference-{model_id[:8]}"
        ).start()

    def _execute_request(self, request: InferenceRequest):
        """Execute an inference request."""
        start_time = time.time()
        queued_time = (start_time - request.created_at) * 1000

        try:
            handler = self._model_handlers.get(request.model_id)
            if not handler:
                raise ValueError(f"No handler for model {request.model_id}")

            output = handler(request.input_data)

            execution_time = (time.time() - start_time) * 1000
            result = InferenceResult(
                request_id=request.request_id,
                model_id=request.model_id,
                output=output,
                execution_time_ms=execution_time,
                queued_time_ms=queued_time,
            )

            with self._lock:
                self._results[request.request_id] = result
                self._completed_requests.append({
                    "request_id": request.request_id,
                    "model_id": request.model_id,
                    "execution_time_ms": execution_time,
                    "queued_time_ms": queued_time,
                    "timestamp": time.time(),
                })
                self._metrics["completed_requests"] += 1
                self._metrics["total_queue_time_ms"] += queued_time
                self._metrics["total_execution_time_ms"] += execution_time

            if request.callback:
                request.callback(result)

        except Exception as e:
            execution_time = (time.time() - start_time) * 1000
            error_result = InferenceResult(
                request_id=request.request_id,
                model_id=request.model_id,
                output=None,
                error=str(e),
                execution_time_ms=execution_time,
                queued_time_ms=queued_time,
            )
            with self._lock:
                self._results[request.request_id] = error_result
                self._metrics["failed_requests"] += 1

        finally:
            with self._lock:
                self._running[request.model_id] = max(0, self._running.get(request.model_id, 0) - 1)
                if request.request_id in self._pending_requests:
                    del self._pending_requests[request.request_id]

    def get_queue_size(self, model_id: str) -> int:
        """Get the current queue size for a model."""
        with self._lock:
            return len(self._queues.get(model_id, []))

    def get_stats(self) -> Dict[str, Any]:
        """Get scheduler statistics."""
        with self._lock:
            total_queued = sum(len(q) for q in self._queues.values())
            total_running = sum(self._running.values())

            avg_queue_time = 0.0
            avg_exec_time = 0.0
            if self._metrics["completed_requests"] > 0:
                avg_queue_time = self._metrics["total_queue_time_ms"] / self._metrics["completed_requests"]
                avg_exec_time = self._metrics["total_execution_time_ms"] / self._metrics["completed_requests"]

            return {
                "running": self._running_flag,
                "total_queued": total_queued,
                "total_running": total_running,
                "max_concurrent_per_model": self._max_concurrent_per_model,
                "registered_models": list(self._model_handlers.keys()),
                "metrics": {
                    **self._metrics,
                    "avg_queue_time_ms": avg_queue_time,
                    "avg_execution_time_ms": avg_exec_time,
                },
                "queue_sizes": {model_id: len(q) for model_id, q in self._queues.items()},
                "running_per_model": dict(self._running),
            }