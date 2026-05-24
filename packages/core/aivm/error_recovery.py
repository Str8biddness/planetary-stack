"""
AIVM Error Recovery System
Provides comprehensive error handling, retry logic, and circuit breakers
for all AIVM components with graceful degradation.
"""
from typing import Dict, Any, Optional, List, Callable, TypeVar, Generic
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import logging
import traceback
from collections import defaultdict
from functools import wraps

logger = logging.getLogger(__name__)


class ErrorSeverity(Enum):
    """Enumeration of error severity levels for AIVM components.

    Attributes:
        WARNING: Non-critical issues that don't disrupt core operations.
        ERROR: Standard operational failures that require attention.
        CRITICAL: Severe issues impacting major system functionality.
        FATAL: Catastrophic failures that require immediate system halt or restart.
    """
    WARNING = "warning"
    ERROR = "error"
    CRITICAL = "critical"
    FATAL = "fatal"


class CircuitState(Enum):
    """Enumeration of possible states for a circuit breaker.

    Attributes:
        CLOSED: Normal operation mode where requests are allowed through.
        OPEN: Failure mode where requests are immediately rejected.
        HALF_OPEN: Recovery mode where a limited number of requests are allowed to test stability.
    """
    CLOSED = "closed"   # Normal operation
    OPEN = "open"       # Failing, reject requests
    HALF_OPEN = "half_open"  # Testing recovery


@dataclass
class ErrorRecord:
    """Data record representing a single error event in the AIVM system.

    Attributes:
        error_id: Unique identifier for the error record.
        component: The name of the component where the error occurred.
        error_type: The category or class of the error.
        message: Human-readable description of the error.
        severity: The severity level (ErrorSeverity).
        timestamp: Unix timestamp of when the error occurred.
        context: Metadata dictionary for additional error context.
        stack_trace: String representation of the exception stack trace.
        resolved: Boolean flag indicating if the error has been addressed.
        resolved_at: Unix timestamp of when the error was marked resolved.
    """
    error_id: str
    component: str
    error_type: str
    message: str
    severity: ErrorSeverity
    timestamp: float
    context: Dict[str, Any] = field(default_factory=dict)
    stack_trace: str = ""
    resolved: bool = False
    resolved_at: Optional[float] = None


@dataclass
class CircuitBreakerConfig:
    """Configuration settings for a CircuitBreaker instance.

    Attributes:
        failure_threshold: Number of consecutive failures before opening the circuit.
        recovery_timeout_seconds: Seconds to wait in OPEN state before trying HALF_OPEN.
        half_open_max_calls: Max successful calls in HALF_OPEN before moving to CLOSED.
        enabled: Whether the circuit breaker logic is active.
    """
    failure_threshold: int = 5
    recovery_timeout_seconds: float = 30.0
    half_open_max_calls: int = 3
    enabled: bool = True


class CircuitBreaker:
    """
    Circuit breaker implementation for AIVM components.
    Prevents cascade failures by failing fast when a component is unhealthy.
    """

    def __init__(self, name: str, config: CircuitBreakerConfig = None):
        """Initializes the CircuitBreaker.

        Args:
            name: Human-readable name for the circuit breaker.
            config: Optional CircuitBreakerConfig instance.
        """
        self._name = name
        self._config = config or CircuitBreakerConfig()
        self._state = CircuitState.CLOSED
        self._failure_count = 0
        self._last_failure_time: Optional[float] = None
        self._half_open_calls = 0
        self._lock = threading.RLock()
        self._stats = {
            "total_calls": 0,
            "successful_calls": 0,
            "rejected_calls": 0,
            "state_changes": 0,
        }

    @property
    def state(self) -> CircuitState:
        """Determines the current state of the circuit breaker, potentially transitioning to half-open.

        Returns:
            The current CircuitState.
        """
        with self._lock:
            if self._state == CircuitState.OPEN:
                if self._last_failure_time and \
                   time.time() - self._last_failure_time >= self._config.recovery_timeout_seconds:
                    self._state = CircuitState.HALF_OPEN
                    self._half_open_calls = 0
                    self._stats["state_changes"] += 1
            return self._state

    def record_success(self):
        """Records a successful operation, potentially closing the circuit if it was half-open."""
        with self._lock:
            self._failure_count = 0
            if self._state == CircuitState.HALF_OPEN:
                self._half_open_calls += 1
                if self._half_open_calls >= self._config.half_open_max_calls:
                    self._state = CircuitState.CLOSED
                    self._failure_count = 0
                    self._stats["state_changes"] += 1
            self._stats["successful_calls"] += 1

    def record_failure(self):
        """Records an operation failure, potentially opening the circuit if thresholds are exceeded."""
        with self._lock:
            self._failure_count += 1
            self._last_failure_time = time.time()
            if self._state == CircuitState.HALF_OPEN:
                self._state = CircuitState.OPEN
                self._stats["state_changes"] += 1
            elif self._failure_count >= self._config.failure_threshold:
                self._state = CircuitState.OPEN
                self._stats["state_changes"] += 1

    def can_execute(self) -> bool:
        """Checks if the component is in a state that allows execution.

        Returns:
            True if execution is allowed, False if the circuit is open.
        """
        if not self._config.enabled:
            return True
        state = self.state
        if state == CircuitState.CLOSED:
            return True
        if state == CircuitState.HALF_OPEN:
            return self._half_open_calls < self._config.half_open_max_calls
        return False

    def get_stats(self) -> Dict[str, Any]:
        """Retrieves operational statistics for the circuit breaker.

        Returns:
            A dictionary containing state, failure counts, and call history.
        """
        with self._lock:
            return {
                "name": self._name,
                "state": self.state.value,
                "failure_count": self._failure_count,
                **self._stats,
            }


def with_circuit_breaker(breaker: CircuitBreaker, fallback: Callable = None):
    """Decorator to wrap a function with circuit breaker protection.

    Args:
        breaker: The CircuitBreaker instance to use.
        fallback: Optional function to call when the circuit is open.

    Returns:
        The decorated function.
    """
    def decorator(fn: Callable) -> Callable:
        """The actual decorator function that wraps the target function.

        Args:
            fn: The function to be decorated.

        Returns:
            The wrapped function with circuit breaker logic.
        """
        @wraps(fn)
        def wrapper(*args, **kwargs):
            """Wrapper function that executes circuit breaker logic around the target function.

            Args:
                *args: Positional arguments for the target function.
                **kwargs: Keyword arguments for the target function.

            Returns:
                The result of the target function or the fallback.

            Raises:
                RuntimeError: If the circuit is open and no fallback is provided.
                Exception: Any exception raised by the target function.
            """
            if not breaker.can_execute():
                logger.warning(f"Circuit breaker {breaker._name} open — rejecting call to {fn.__name__}")
                if fallback:
                    return fallback(*args, **kwargs)
                raise RuntimeError(f"Circuit breaker {breaker._name} is open")
            try:
                result = fn(*args, **kwargs)
                breaker.record_success()
                return result
            except Exception as e:
                breaker.record_failure()
                raise
        return wrapper
    return decorator


class ErrorRecoveryManager:
    """
    Central error recovery manager for AIVM.
    Tracks errors, manages circuit breakers, and coordinates recovery actions.
    """

    def __init__(self, max_error_history: int = 500):
        """Initializes the ErrorRecoveryManager.

        Args:
            max_error_history: Maximum number of error records to retain. Defaults to 500.
        """
        self._errors: Dict[str, ErrorRecord] = {}
        self._error_sequence = 0
        self._lock = threading.RLock()
        self._max_history = max_error_history

        self._circuit_breakers: Dict[str, CircuitBreaker] = {}
        self._recovery_handlers: Dict[str, List[Callable]] = defaultdict(list)
        self._stats = {
            "total_errors": 0,
            "resolved_errors": 0,
            "recovery_attempts": 0,
            "recovery_successes": 0,
        }

    def register_circuit_breaker(self, name: str, config: CircuitBreakerConfig = None) -> CircuitBreaker:
        """Registers a new circuit breaker with the manager.

        Args:
            name: Unique name for the breaker.
            config: Optional configuration.

        Returns:
            The registered CircuitBreaker instance.
        """
        with self._lock:
            if name not in self._circuit_breakers:
                self._circuit_breakers[name] = CircuitBreaker(name, config)
            return self._circuit_breakers[name]

    def get_circuit_breaker(self, name: str) -> Optional[CircuitBreaker]:
        """Retrieves a registered circuit breaker by name.

        Args:
            name: The name of the breaker.

        Returns:
            The CircuitBreaker instance if found, otherwise None.
        """
        return self._circuit_breakers.get(name)

    def register_recovery_handler(self, component: str, handler: Callable):
        """Registers a custom recovery handler for a specific component.

        Args:
            component: The component name to handle.
            handler: A callable that accepts an ErrorRecord.
        """
        self._recovery_handlers[component].append(handler)

    def record_error(
        self,
        component: str,
        error_type: str,
        message: str,
        severity: ErrorSeverity = ErrorSeverity.ERROR,
        context: Dict[str, Any] = None,
        exception: Exception = None,
    ) -> str:
        """Logs an error and potentially triggers automated recovery logic.

        Args:
            component: The component where the error occurred.
            error_type: Category of the error.
            message: Descriptive error message.
            severity: ErrorSeverity level. Defaults to ERROR.
            context: Optional dictionary of additional metadata.
            exception: Optional Exception instance for stack trace capture.

        Returns:
            The unique ID of the created ErrorRecord.
        """
        with self._lock:
            error_id = f"err_{self._error_sequence}"
            self._error_sequence += 1

            record = ErrorRecord(
                error_id=error_id,
                component=component,
                error_type=error_type,
                message=message,
                severity=severity,
                timestamp=time.time(),
                context=context or {},
                stack_trace=traceback.format_exc() if exception else "",
            )

            self._errors[error_id] = record
            self._stats["total_errors"] += 1

            if len(self._errors) > self._max_history:
                oldest = min(self._errors.items(), key=lambda x: x[1].timestamp)
                del self._errors[oldest[0]]

        logger.error(f"Error in {component} ({severity.value}): {message}")
        if exception:
            logger.debug(f"Stack trace: {traceback.format_exc()}")

        if severity in (ErrorSeverity.ERROR, ErrorSeverity.CRITICAL, ErrorSeverity.FATAL):
            self._trigger_recovery(component, record)

        return error_id

    def _trigger_recovery(self, component: str, record: ErrorRecord):
        """Executes all registered recovery handlers for a given component and error.

        Args:
            component: The component requiring recovery.
            record: The ErrorRecord that triggered recovery.
        """
        handlers = self._recovery_handlers.get(component, [])
        if not handlers:
            return

        for handler in handlers:
            try:
                self._stats["recovery_attempts"] += 1
                handler(record)
                self._stats["recovery_successes"] += 1
                logger.info(f"Recovery handler succeeded for {component}")
            except Exception as e:
                logger.error(f"Recovery handler failed for {component}: {e}")

    def resolve_error(self, error_id: str) -> bool:
        """Marks a recorded error as resolved.

        Args:
            error_id: The ID of the error to resolve.

        Returns:
            True if the error was found and marked resolved, False otherwise.
        """
        with self._lock:
            if error_id not in self._errors:
                return False
            self._errors[error_id].resolved = True
            self._errors[error_id].resolved_at = time.time()
            self._stats["resolved_errors"] += 1
            return True

    def get_unresolved_errors(self, component: str = None) -> List[ErrorRecord]:
        """Retrieves all errors that have not yet been marked as resolved.

        Args:
            component: Optional component filter.

        Returns:
            A list of unresolved ErrorRecord objects.
        """
        with self._lock:
            errors = [e for e in self._errors.values() if not e.resolved]
            if component:
                errors = [e for e in errors if e.component == component]
            return errors

    def get_stats(self) -> Dict[str, Any]:
        """Generates aggregate statistics for all tracked errors and circuit breakers.

        Returns:
            A dictionary containing summary counts and breaker states.
        """
        with self._lock:
            unresolved_by_severity = defaultdict(int)
            for e in self._errors.values():
                if not e.resolved:
                    unresolved_by_severity[e.severity.value] += 1

            return {
                **self._stats,
                "total_tracked_errors": len(self._errors),
                "unresolved_errors": len([e for e in self._errors.values() if not e.resolved]),
                "unresolved_by_severity": dict(unresolved_by_severity),
                "circuit_breakers": {
                    name: cb.get_stats()
                    for name, cb in self._circuit_breakers.items()
                },
            }


def retry_with_backoff(
    max_attempts: int = 3,
    base_delay_seconds: float = 0.5,
    max_delay_seconds: float = 10.0,
    exponential_base: float = 2.0,
    retriable_exceptions: tuple = (Exception,),
):
    """Decorator that implements exponential backoff retry logic for a function.

    Args:
        max_attempts: Maximum number of calls to attempt. Defaults to 3.
        base_delay_seconds: Initial delay after the first failure. Defaults to 0.5.
        max_delay_seconds: Maximum capped delay between retries. Defaults to 10.0.
        exponential_base: Base for exponential increase (e.g. 2.0 = doubling). Defaults to 2.0.
        retriable_exceptions: Tuple of exception types that should trigger a retry.

    Returns:
        The decorated function.
    """
    def decorator(fn: Callable) -> Callable:
        """The actual decorator function that wraps the target function.

        Args:
            fn: The function to be decorated.

        Returns:
            The wrapped function with retry logic.
        """
        @wraps(fn)
        def wrapper(*args, **kwargs):
            """Wrapper function that executes the target function with retry attempts.

            Args:
                *args: Positional arguments for the target function.
                **kwargs: Keyword arguments for the target function.

            Returns:
                The result of the target function if it succeeds within max_attempts.

            Raises:
                Exception: The last exception encountered if all retry attempts fail.
            """
            last_exception = None
            for attempt in range(max_attempts):
                try:
                    return fn(*args, **kwargs)
                except retriable_exceptions as e:
                    last_exception = e
                    if attempt < max_attempts - 1:
                        delay = min(base_delay_seconds * (exponential_base ** attempt), max_delay_seconds)
                        logger.warning(
                            f"Attempt {attempt + 1}/{max_attempts} failed for {fn.__name__}: {e}. "
                            f"Retrying in {delay:.1f}s"
                        )
                        time.sleep(delay)
                    else:
                        logger.error(f"All {max_attempts} attempts failed for {fn.__name__}")
            raise last_exception
        return wrapper
    return decorator