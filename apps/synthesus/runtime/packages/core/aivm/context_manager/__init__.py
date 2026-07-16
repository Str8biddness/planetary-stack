"""
AIVM Execution Context Manager
Manages isolated execution contexts for concurrent Synthesus models.
"""
from typing import Dict, Any, Optional, List, Callable
from dataclasses import dataclass, field
from enum import Enum
import threading
import time
import uuid
import logging
import copy

logger = logging.getLogger(__name__)


class ContextState(Enum):
    """Lifecycle states for execution contexts.
    
    Attributes:
        CREATED: Context created but not yet initialized
        INITIALIZING: Context is being initialized
        READY: Context initialized and ready to run
        RUNNING: Context is actively executing
        PAUSED: Context execution is paused
        ERROR: Context encountered an error
        TERMINATED: Context has been terminated
    """
    CREATED = "created"
    INITIALIZING = "initializing"
    READY = "ready"
    RUNNING = "running"
    PAUSED = "paused"
    ERROR = "error"
    TERMINATED = "terminated"


@dataclass
class ExecutionContext:
    """Isolated execution context for a model inference session.
    
    Attributes:
        context_id: Unique context identifier
        model_id: ID of the model this context is for
        state: Current ContextState
        created_at: Timestamp when context was created
        last_active_at: Timestamp of last activity
        session_data: Arbitrary session data key-value store
        metadata: Additional context metadata
        parent_context_id: Parent context ID for nested contexts
        isolation_level: Isolation level (1=basic, higher=more isolated)
    """
    context_id: str
    model_id: str
    state: ContextState = ContextState.CREATED
    created_at: float = field(default_factory=time.time)
    last_active_at: float = field(default_factory=time.time)
    session_data: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    parent_context_id: Optional[str] = None
    isolation_level: int = 1


@dataclass
class ContextSnapshot:
    """Point-in-time snapshot of an ExecutionContext for rollback/debugging.
    
    Attributes:
        context_id: ID of the context being snapshotted
        model_id: ID of the model
        state: Context state at snapshot time
        session_data: Deep copy of session data
        metadata: Deep copy of metadata
        captured_at: Timestamp when snapshot was taken
    """
    context_id: str
    model_id: str
    state: ContextState
    session_data: Dict[str, Any]
    metadata: Dict[str, Any]
    captured_at: float


class ExecutionContextManager:
    """
    Manages execution contexts for concurrent AIVM models.
    Provides context isolation, state management, and checkpoint/restore.
    """

    def __init__(self, max_contexts: int = 64):
        self._contexts: Dict[str, ExecutionContext] = {}
        self._max_contexts = max_contexts
        self._lock = threading.RLock()
        self._state_listeners: Dict[ContextState, List[Callable]] = {
            state: [] for state in ContextState
        }
        self._snapshots: Dict[str, List[ContextSnapshot]] = {}
        self._context_history: List[Dict[str, Any]] = []

    def create_context(
        self,
        model_id: str,
        session_data: Dict[str, Any] = None,
        metadata: Dict[str, Any] = None,
        parent_context_id: Optional[str] = None,
        isolation_level: int = 1
    ) -> str:
        """Create a new execution context for a model."""
        if len(self._contexts) >= self._max_contexts:
            oldest = min(self._contexts.values(), key=lambda c: c.last_active_at)
            self.terminate_context(oldest.context_id)
            logger.info(f"Evicted oldest context {oldest.context_id} to make room")

        context_id = str(uuid.uuid4())
        context = ExecutionContext(
            context_id=context_id,
            model_id=model_id,
            state=ContextState.CREATED,
            session_data=session_data or {},
            metadata=metadata or {},
            parent_context_id=parent_context_id,
            isolation_level=isolation_level,
        )

        with self._lock:
            self._contexts[context_id] = context
            self._snapshots[context_id] = []

        logger.info(f"Created context {context_id} for model {model_id}")
        self._record_event(context_id, "created")
        return context_id

    def get_context(self, context_id: str) -> Optional[ExecutionContext]:
        """Get a context by ID."""
        return self._contexts.get(context_id)

    def get_context_by_model(self, model_id: str) -> Optional[ExecutionContext]:
        """Get the active context for a model."""
        with self._lock:
            for ctx in self._contexts.values():
                if ctx.model_id == model_id and ctx.state in (ContextState.READY, ContextState.RUNNING):
                    return ctx
        return None

    def list_contexts(self, model_id: str = None, state: ContextState = None) -> List[ExecutionContext]:
        """List contexts with optional filtering."""
        with self._lock:
            contexts = list(self._contexts.values())
        if model_id:
            contexts = [c for c in contexts if c.model_id == model_id]
        if state:
            contexts = [c for c in contexts if c.state == state]
        return contexts

    def initialize_context(self, context_id: str) -> bool:
        """Initialize a context (transition to READY state)."""
        context = self._contexts.get(context_id)
        if not context:
            return False

        with self._lock:
            context.state = ContextState.INITIALIZING

        context.state = ContextState.READY
        context.last_active_at = time.time()
        self._record_event(context_id, "initialized")
        self._notify_state_change(context)
        logger.info(f"Context {context_id} initialized")
        return True

    def run_context(self, context_id: str) -> bool:
        """Mark a context as running."""
        context = self._contexts.get(context_id)
        if not context or context.state != ContextState.READY:
            return False

        context.state = ContextState.RUNNING
        context.last_active_at = time.time()
        self._record_event(context_id, "running")
        self._notify_state_change(context)
        return True

    def pause_context(self, context_id: str) -> bool:
        """Pause a running context."""
        context = self._contexts.get(context_id)
        if not context or context.state != ContextState.RUNNING:
            return False

        context.state = ContextState.PAUSED
        context.last_active_at = time.time()
        self._record_event(context_id, "paused")
        self._notify_state_change(context)
        return True

    def resume_context(self, context_id: str) -> bool:
        """Resume a paused context."""
        context = self._contexts.get(context_id)
        if not context or context.state != ContextState.PAUSED:
            return False

        context.state = ContextState.RUNNING
        context.last_active_at = time.time()
        self._record_event(context_id, "resumed")
        self._notify_state_change(context)
        return True

    def terminate_context(self, context_id: str) -> bool:
        """Terminate a context."""
        context = self._contexts.get(context_id)
        if not context:
            return False

        old_state = context.state
        context.state = ContextState.TERMINATED
        self._record_event(context_id, "terminated")
        self._notify_state_change(context)

        with self._lock:
            if context_id in self._contexts:
                del self._contexts[context_id]
            if context_id in self._snapshots:
                del self._snapshots[context_id]

        logger.info(f"Context {context_id} terminated (was {old_state.value})")
        return True

    def update_session_data(self, context_id: str, key: str, value: Any) -> bool:
        """Update session data in a context."""
        context = self._contexts.get(context_id)
        if not context:
            return False

        context.session_data[key] = value
        context.last_active_at = time.time()
        return True

    def get_session_data(self, context_id: str, key: str) -> Any:
        """Get session data from a context."""
        context = self._contexts.get(context_id)
        if not context:
            return None
        return context.session_data.get(key)

    def clear_session_data(self, context_id: str) -> bool:
        """Clear all session data."""
        context = self._contexts.get(context_id)
        if not context:
            return False
        context.session_data.clear()
        return True

    def snapshot_context(self, context_id: str) -> Optional[ContextSnapshot]:
        """Create a snapshot of a context."""
        context = self._contexts.get(context_id)
        if not context:
            return None

        snapshot = ContextSnapshot(
            context_id=context.context_id,
            model_id=context.model_id,
            state=context.state,
            session_data=copy.deepcopy(context.session_data),
            metadata=copy.deepcopy(context.metadata),
            captured_at=time.time(),
        )

        with self._lock:
            if context_id in self._snapshots:
                self._snapshots[context_id].append(snapshot)
            else:
                self._snapshots[context_id] = [snapshot]

        self._record_event(context_id, "snapshot_created")
        return snapshot

    def restore_context(self, context_id: str, snapshot: ContextSnapshot) -> bool:
        """Restore a context from a snapshot."""
        context = self._contexts.get(context_id)
        if not context:
            return False

        context.session_data = copy.deepcopy(snapshot.session_data)
        context.metadata = copy.deepcopy(snapshot.metadata)
        context.last_active_at = time.time()
        self._record_event(context_id, "restored")
        return True

    def get_snapshots(self, context_id: str) -> List[ContextSnapshot]:
        """Get all snapshots for a context."""
        return self._snapshots.get(context_id, [])

    def register_state_listener(self, state: ContextState, listener: Callable):
        """Register a listener for context state changes."""
        self._state_listeners[state].append(listener)

    def _notify_state_change(self, context: ExecutionContext):
        """Notify listeners of a state change."""
        listeners = self._state_listeners.get(context.state, [])
        for listener in listeners:
            try:
                listener(context)
            except Exception as e:
                logger.error(f"State listener error: {e}")

    def _record_event(self, context_id: str, event: str):
        """Record a context event."""
        self._context_history.append({
            "context_id": context_id,
            "event": event,
            "timestamp": time.time(),
        })
        if len(self._context_history) > 1000:
            self._context_history = self._context_history[-500:]

    def get_stats(self) -> Dict[str, Any]:
        """Get context manager statistics."""
        with self._lock:
            state_counts = {s.value: 0 for s in ContextState}
            for ctx in self._contexts.values():
                state_counts[ctx.state.value] += 1

            return {
                "total_contexts": len(self._contexts),
                "max_contexts": self._max_contexts,
                "state_breakdown": state_counts,
                "total_snapshots": sum(len(s) for s in self._snapshots.values()),
                "history_size": len(self._context_history),
            }