"""
Reasoning Tracer — Deep Hemisphere Trace Capture & Real-time Streaming

Captures step-by-step reasoning from all 4 hemispheres (MC, NS, Psi, VO):
- Policy/Monte Carlo (MC): Intent classification, action planning
- Risk/Novelty Search (NS): Threat detection, uncertainty quantification  
- Attention/Psi: Focus areas, pattern recognition
- Value/VO: Outcome evaluation, value alignment

Supports:
- A) Deep traces with full hemisphere state snapshots
- B) Real-time streaming via callbacks/async generators
- C) Interactive drill-down with trace IDs for later inspection
"""

import asyncio
import json
import time
import uuid
from dataclasses import dataclass, field, asdict
from typing import Any, Dict, List, Optional, Callable, AsyncGenerator
from datetime import datetime
from enum import Enum
import logging

logger = logging.getLogger(__name__)


class Hemisphere(Enum):
    """The four hemispheres of the quad-brain."""
    MC = "MC"  # Policy / Monte Carlo / Brain 2
    NS = "NS"  # Risk / Novelty Search / Brain 1
    PSI = "Psi"  # Attention / Fluid / Brain 3
    VO = "VO"  # Value / Outcome / Brain 4


class TraceEventType(Enum):
    """Types of trace events."""
    HEMISPHERE_START = "hemisphere_start"
    HEMISPHERE_COMPLETE = "hemisphere_complete"
    KNOWLEDGE_RETRIEVAL = "knowledge_retrieval"
    PATTERN_MATCH = "pattern_match"
    DECISION_POINT = "decision_point"
    CONFIDENCE_UPDATE = "confidence_update"
    INTEGRATION = "integration"
    EXECUTION_START = "execution_start"
    EXECUTION_COMPLETE = "execution_complete"
    STREAM_TOKEN = "stream_token"


@dataclass
class HemisphereState:
    """Snapshot of a hemisphere's state during processing."""
    hemisphere: Hemisphere
    timestamp: float
    inputs: Dict[str, Any] = field(default_factory=dict)
    outputs: Dict[str, Any] = field(default_factory=dict)
    confidence: float = 0.0
    latency_ms: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)


@dataclass
class TraceEvent:
    """A single event in the reasoning trace."""
    event_id: str
    trace_id: str
    event_type: TraceEventType
    hemisphere: Optional[Hemisphere]
    timestamp: float
    data: Dict[str, Any] = field(default_factory=dict)
    parent_event_id: Optional[str] = None
    depth: int = 0


@dataclass
class ReasoningTrace:
    """Complete reasoning trace for a single query."""
    trace_id: str
    query: str
    character_id: str
    start_time: float
    end_time: Optional[float] = None
    events: List[TraceEvent] = field(default_factory=list)
    hemisphere_states: Dict[Hemisphere, List[HemisphereState]] = field(default_factory=lambda: {
        h: [] for h in Hemisphere
    })
    final_answer: Optional[str] = None
    overall_confidence: float = 0.0
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert trace to dictionary for serialization."""
        return {
            "trace_id": self.trace_id,
            "query": self.query,
            "character_id": self.character_id,
            "start_time": self.start_time,
            "end_time": self.end_time,
            "duration_ms": (self.end_time - self.start_time) * 1000 if self.end_time else None,
            "event_count": len(self.events),
            "hemisphere_summary": {
                h.value: len(states) for h, states in self.hemisphere_states.items()
            },
            "final_answer": self.final_answer,
            "overall_confidence": self.overall_confidence,
            "metadata": self.metadata,
        }
    
    def get_events_by_type(self, event_type: TraceEventType) -> List[TraceEvent]:
        """Get all events of a specific type."""
        return [e for e in self.events if e.event_type == event_type]
    
    def get_hemisphere_timeline(self, hemisphere: Hemisphere) -> List[HemisphereState]:
        """Get all state snapshots for a hemisphere."""
        return self.hemisphere_states.get(hemisphere, [])


class StreamingManager:
    """Manages real-time streaming of reasoning events."""
    
    def __init__(self):
        self._streams: Dict[str, List[asyncio.Queue]] = {}
        self._callbacks: List[Callable[[TraceEvent], None]] = []
    
    def register_callback(self, callback: Callable[[TraceEvent], None]):
        """Register a callback for all events."""
        self._callbacks.append(callback)
    
    def create_stream(self, trace_id: str) -> asyncio.Queue:
        """Create a new stream for a trace."""
        queue = asyncio.Queue()
        if trace_id not in self._streams:
            self._streams[trace_id] = []
        self._streams[trace_id].append(queue)
        return queue
    
    async def emit(self, trace_id: str, event: TraceEvent):
        """Emit an event to all subscribers."""
        # Call synchronous callbacks
        for callback in self._callbacks:
            try:
                callback(event)
            except Exception as e:
                logger.error(f"Stream callback error: {e}")
        
        # Send to async streams
        if trace_id in self._streams:
            for queue in self._streams[trace_id]:
                await queue.put(event)
    
    async def event_generator(self, trace_id: str) -> AsyncGenerator[TraceEvent, None]:
        """Generate events for a trace."""
        queue = self.create_stream(trace_id)
        try:
            while True:
                event = await queue.get()
                if event.event_type == TraceEventType.EXECUTION_COMPLETE:
                    yield event
                    break
                yield event
        finally:
            if trace_id in self._streams and queue in self._streams[trace_id]:
                self._streams[trace_id].remove(queue)


class ReasoningTracer:
    """
    Captures detailed reasoning traces from the quad-brain architecture.
    
    Features:
    - Deep hemisphere state capture
    - Real-time streaming
    - Persistent trace storage
    - Interactive drill-down support
    """
    
    def __init__(self, enable_streaming: bool = True):
        self.traces: Dict[str, ReasoningTrace] = {}
        self.streaming = StreamingManager() if enable_streaming else None
        self._active_traces: Dict[str, ReasoningTrace] = {}
    
    def start_trace(self, query: str, character_id: str, **metadata) -> str:
        """Start a new reasoning trace."""
        trace_id = str(uuid.uuid4())
        trace = ReasoningTrace(
            trace_id=trace_id,
            query=query,
            character_id=character_id,
            start_time=time.time(),
            metadata=metadata,
        )
        self._active_traces[trace_id] = trace
        return trace_id
    
    def add_event(
        self,
        trace_id: str,
        event_type: TraceEventType,
        hemisphere: Optional[Hemisphere] = None,
        data: Optional[Dict[str, Any]] = None,
        parent_event_id: Optional[str] = None,
    ) -> str:
        """Add an event to a trace."""
        if trace_id not in self._active_traces:
            logger.warning(f"Trace {trace_id} not found")
            return ""
        
        trace = self._active_traces[trace_id]
        
        # Calculate depth from parent
        depth = 0
        if parent_event_id:
            for e in trace.events:
                if e.event_id == parent_event_id:
                    depth = e.depth + 1
                    break
        
        event = TraceEvent(
            event_id=str(uuid.uuid4()),
            trace_id=trace_id,
            event_type=event_type,
            hemisphere=hemisphere,
            timestamp=time.time(),
            data=data or {},
            parent_event_id=parent_event_id,
            depth=depth,
        )
        
        trace.events.append(event)
        
        # Stream if enabled
        if self.streaming:
            asyncio.create_task(self.streaming.emit(trace_id, event))
        
        return event.event_id
    
    def capture_hemisphere_state(
        self,
        trace_id: str,
        hemisphere: Hemisphere,
        inputs: Dict[str, Any],
        outputs: Dict[str, Any],
        confidence: float,
        latency_ms: float,
        metadata: Optional[Dict[str, Any]] = None,
    ):
        """Capture a hemisphere state snapshot."""
        if trace_id not in self._active_traces:
            return
        
        trace = self._active_traces[trace_id]
        state = HemisphereState(
            hemisphere=hemisphere,
            timestamp=time.time(),
            inputs=inputs,
            outputs=outputs,
            confidence=confidence,
            latency_ms=latency_ms,
            metadata=metadata or {},
        )
        
        trace.hemisphere_states[hemisphere].append(state)
        
        # Also add as event
        self.add_event(
            trace_id=trace_id,
            event_type=TraceEventType.HEMISPHERE_COMPLETE,
            hemisphere=hemisphere,
            data={
                "confidence": confidence,
                "latency_ms": latency_ms,
                "output_summary": str(outputs)[:200],
            },
        )
    
    def end_trace(
        self,
        trace_id: str,
        final_answer: str,
        overall_confidence: float,
    ) -> ReasoningTrace:
        """End a trace and save it."""
        if trace_id not in self._active_traces:
            raise ValueError(f"Trace {trace_id} not found")
        
        trace = self._active_traces[trace_id]
        trace.end_time = time.time()
        trace.final_answer = final_answer
        trace.overall_confidence = overall_confidence
        
        # Add completion event
        self.add_event(
            trace_id=trace_id,
            event_type=TraceEventType.EXECUTION_COMPLETE,
            data={
                "final_answer": final_answer[:500],
                "overall_confidence": overall_confidence,
                "duration_ms": (trace.end_time - trace.start_time) * 1000,
            },
        )
        
        # Move to completed traces
        self.traces[trace_id] = trace
        del self._active_traces[trace_id]
        
        return trace
    
    def get_trace(self, trace_id: str) -> Optional[ReasoningTrace]:
        """Get a completed trace by ID."""
        return self.traces.get(trace_id)
    
    def get_active_trace(self, trace_id: str) -> Optional[ReasoningTrace]:
        """Get an active (in-progress) trace by ID."""
        return self._active_traces.get(trace_id)
    
    def list_traces(
        self,
        character_id: Optional[str] = None,
        limit: int = 100,
    ) -> List[Dict[str, Any]]:
        """List traces with optional filtering."""
        traces = list(self.traces.values())
        
        if character_id:
            traces = [t for t in traces if t.character_id == character_id]
        
        # Sort by start time descending
        traces.sort(key=lambda t: t.start_time, reverse=True)
        
        return [t.to_dict() for t in traces[:limit]]
    
    async def stream_trace(self, trace_id: str) -> AsyncGenerator[Dict[str, Any], None]:
        """Stream events for a trace in real-time."""
        if not self.streaming:
            raise RuntimeError("Streaming not enabled")
        
        async for event in self.streaming.event_generator(trace_id):
            yield {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "hemisphere": event.hemisphere.value if event.hemisphere else None,
                "timestamp": event.timestamp,
                "data": event.data,
                "depth": event.depth,
            }
    
    def drill_down(self, trace_id: str, event_id: str) -> Optional[Dict[str, Any]]:
        """
        Drill down into a specific event to see detailed information.
        
        For interactive "Why?" exploration of specific reasoning steps.
        """
        trace = self.traces.get(trace_id) or self._active_traces.get(trace_id)
        if not trace:
            return None
        
        # Find the event
        event = None
        for e in trace.events:
            if e.event_id == event_id:
                event = e
                break
        
        if not event:
            return None
        
        # Get related events (children and siblings)
        children = [e for e in trace.events if e.parent_event_id == event_id]
        siblings = []
        if event.parent_event_id:
            siblings = [
                e for e in trace.events
                if e.parent_event_id == event.parent_event_id and e.event_id != event_id
            ]
        
        # Get hemisphere state if applicable
        hemisphere_states = []
        if event.hemisphere:
            states = trace.hemisphere_states.get(event.hemisphere, [])
            # Find states close to this event's timestamp
            for state in states:
                if abs(state.timestamp - event.timestamp) < 0.1:  # Within 100ms
                    hemisphere_states.append({
                        "timestamp": state.timestamp,
                        "inputs": state.inputs,
                        "outputs": state.outputs,
                        "confidence": state.confidence,
                        "latency_ms": state.latency_ms,
                        "metadata": state.metadata,
                    })
        
        return {
            "event": {
                "event_id": event.event_id,
                "event_type": event.event_type.value,
                "hemisphere": event.hemisphere.value if event.hemisphere else None,
                "timestamp": event.timestamp,
                "data": event.data,
                "depth": event.depth,
                "parent_event_id": event.parent_event_id,
            },
            "children": [
                {"event_id": e.event_id, "event_type": e.event_type.value, "data": e.data}
                for e in children
            ],
            "siblings": [
                {"event_id": e.event_id, "event_type": e.event_type.value}
                for e in siblings
            ],
            "hemisphere_states": hemisphere_states,
            "context": {
                "query": trace.query,
                "character_id": trace.character_id,
                "overall_confidence": trace.overall_confidence,
            },
        }


# Singleton instance
_tracer_instance: Optional[ReasoningTracer] = None


def get_tracer(enable_streaming: bool = True) -> ReasoningTracer:
    """Get or create the reasoning tracer singleton."""
    global _tracer_instance
    if _tracer_instance is None:
        _tracer_instance = ReasoningTracer(enable_streaming=enable_streaming)
    return _tracer_instance
