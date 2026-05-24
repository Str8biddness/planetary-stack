#!/usr/bin/env python3
"""Dual-hemisphere orchestration for Synthesus."""

from __future__ import annotations

import asyncio
import inspect
import json
import logging
import select
import subprocess
import time
from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Awaitable, Callable, Dict, Optional

from bridge import BridgeMode as KernelBridgeMode
from bridge import KernelBridge, KernelQuery
from cognitive.social_fabric import SocialFabric, FactionRelation

logger = logging.getLogger(__name__)


class HemisphereMode(Enum):
    LEFT = "left"
    RIGHT = "right"
    BOTH = "both"
    AUTO = "auto"


@dataclass
class HemisphereResult:
    response: str
    hemisphere_used: str
    raw_confidence: float
    agreement_score: Optional[float] = None
    left_response: Optional[str] = None
    right_response: Optional[str] = None
    latency_ms: float = 0.0
    state_handoff: Optional[Dict[str, Any]] = None


@dataclass
class HemisphereSignal:
    signal_id: str
    source: str
    target: str
    kind: str
    payload: Dict[str, Any]
    created_at: float = field(default_factory=time.time)


@dataclass
class HemisphereState:
    query: str = ""
    character_id: str = ""
    mode: str = "auto"
    rag_context: str = ""
    left_response: str = ""
    right_response: str = ""
    left_confidence: float = 0.0
    right_confidence: float = 0.0
    left_source: str = ""
    right_source: str = ""
    agreement_score: float = 0.0
    character_context: Dict[str, Any] = field(default_factory=dict)
    metadata: Dict[str, Any] = field(default_factory=dict)
    signals: list[Dict[str, Any]] = field(default_factory=list)
    arbitration: Dict[str, Any] = field(default_factory=dict)
    final_response: str = ""
    updated_at: float = 0.0


class HemisphereBridge:
    """Coordinates left- and right-hemisphere processing."""

    def __init__(
        self,
        kernel_bin: str = "./build/zo_kernel",
        kernel_timeout: float = 2.0,
        agreement_threshold: float = 0.65,
        left_config: Optional[Dict[str, Any]] = None,
        right_config: Optional[Dict[str, Any]] = None,
        right_handler: Optional[Any] = None,
        shared_state: Optional[Dict[str, Any]] = None,
    ):
        """Initializes the HemisphereBridge.

        Args:
            kernel_bin: Path to the C++ kernel binary. Defaults to "./build/zo_kernel".
            kernel_timeout: Timeout for kernel queries in seconds. Defaults to 2.0.
            agreement_threshold: Threshold for hemisphere agreement. Defaults to 0.65.
            left_config: Configuration for the left hemisphere. Defaults to None.
            right_config: Configuration for the right hemisphere. Defaults to None.
            right_handler: Optional handler instance for the right hemisphere. Defaults to None.
            shared_state: Optional shared state dictionary. Defaults to None.
        """
        self.kernel_bin = kernel_bin
        self.kernel_timeout = kernel_timeout
        self.agreement_threshold = agreement_threshold
        self.left_config = left_config or {}
        self.right_config = right_config or {}
        self._right_handler = right_handler or self.right_config.get("right_handler")
        self._shared_state = shared_state if shared_state is not None else {}

        self._queries_total = 0
        self._left_wins = 0
        self._right_wins = 0
        self._agreement_count = 0
        self._agreement_sum = 0.0

        # Social Integration
        self._social_fabric = SocialFabric() # Singleton access
        
        self._kernel_proc: Optional[subprocess.Popen] = None
        self._python_bridge = KernelBridge(force_mode=KernelBridgeMode.FALLBACK)
        self._apply_left_routes()
        self._start_kernel()

    def _apply_left_routes(self) -> None:
        """Seeds initial routes into the Python fallback left bridge."""
        routes = self.left_config.get("routes", [])
        for route in routes:
            if not isinstance(route, dict):
                continue
            pattern = route.get("pattern") or route.get("trigger")
            module = route.get("module") or route.get("response")
            if not pattern or not module:
                continue
            try:
                self._python_bridge.ppbrs.add_route(
                    str(pattern),
                    str(module),
                    priority=float(route.get("priority", 1.0)),
                )
            except Exception as exc:
                logger.warning("Failed to seed fallback left route %r: %s", route, exc)

    def _start_kernel(self) -> None:
        """Starts the C++ kernel process."""
        try:
            self._kernel_proc = subprocess.Popen(
                [self.kernel_bin],
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                bufsize=1,
            )
            logger.info("Kernel started (PID %s)", self._kernel_proc.pid)
        except FileNotFoundError:
            logger.warning("Kernel binary not found at %s. Left hemisphere using Python fallback.", self.kernel_bin)
            self._kernel_proc = None
        except Exception as exc:
            logger.warning("Kernel start failed (%s). Left hemisphere using Python fallback.", exc)
            self._kernel_proc = None

    def ping_kernel(self) -> bool:
        """Checks if the kernel process is alive.

        Returns:
            True if the kernel is running, False otherwise.
        """
        return self._kernel_proc is not None and self._kernel_proc.poll() is None

    def _query_python_left(self, query: str, character_id: Optional[str] = None, rag_context: str = "") -> Dict[str, Any]:
        """Queries the Python fallback for the left hemisphere.

        Args:
            query: The input query.
            character_id: Optional character ID. Defaults to None.
            rag_context: Optional RAG context. Defaults to "".

        Returns:
            A dictionary containing the response and confidence.
        """
        kernel_query = KernelQuery(
            text=query,
            context=rag_context,
            character_id=character_id or "",
            metadata={"hemisphere": "left"},
        )
        result = self._python_bridge.query(kernel_query)
        return {
            "response": result.response,
            "confidence": float(result.confidence),
            "found": result.module_used != "fallback" or bool(result.response),
            "module_used": result.module_used,
            "source": "python_fallback",
        }

    def _query_kernel(self, query: str, character_id: Optional[str] = None, rag_context: str = "") -> Dict[str, Any]:
        """Queries the C++ kernel for the left hemisphere.

        Args:
            query: The input query.
            character_id: Optional character ID. Defaults to None.
            rag_context: Optional RAG context. Defaults to "".

        Returns:
            A dictionary containing the response and confidence.
        """
        if not self.ping_kernel():
            return self._query_python_left(query, character_id, rag_context)

        payload = json.dumps(
            {
                "query": query,
                "character_id": character_id or "",
                "rag_context": rag_context,
            }
        ) + "\n"

        try:
            assert self._kernel_proc is not None
            assert self._kernel_proc.stdin is not None
            assert self._kernel_proc.stdout is not None
            self._kernel_proc.stdin.write(payload)
            self._kernel_proc.stdin.flush()

            ready, _, _ = select.select([self._kernel_proc.stdout], [], [], self.kernel_timeout)
            if not ready:
                logger.warning("Kernel timed out after %.2fs; using Python fallback.", self.kernel_timeout)
                return self._query_python_left(query, character_id, rag_context)

            line = self._kernel_proc.stdout.readline()
            if not line:
                logger.warning("Kernel stdout closed; using Python fallback.")
                self._start_kernel()
                return self._query_python_left(query, character_id, rag_context)

            result = json.loads(line.strip())
            return {
                "response": str(result.get("response", "")),
                "confidence": float(result.get("confidence", 0.0)),
                "found": bool(result.get("found", False)),
                "module_used": str(result.get("module_used", result.get("hemisphere_id", "kernel"))),
                "source": "cpp_kernel",
            }
        except Exception as exc:
            logger.warning("Kernel query failed (%s); using Python fallback.", exc)
            self._start_kernel()
            return self._query_python_left(query, character_id, rag_context)

    def _emit_signal(self, source: str, target: str, kind: str, payload: Dict[str, Any]) -> Dict[str, Any]:
        """Append a cross-hemisphere signal to the shared buffer."""
        signal = HemisphereSignal(
            signal_id=f"{source}:{target}:{kind}:{int(time.time() * 1000)}",
            source=source,
            target=target,
            kind=kind,
            payload=payload,
        )
        signal_dict = {
            "signal_id": signal.signal_id,
            "source": signal.source,
            "target": signal.target,
            "kind": signal.kind,
            "payload": signal.payload,
            "created_at": signal.created_at,
        }
        signals = self._shared_state.setdefault("signals", [])
        signals.append(signal_dict)
        if len(signals) > 25:
            del signals[:-25]
        self._shared_state["last_signal"] = signal_dict
        return signal_dict

    def _estimate_right_confidence(self, right_context: Dict[str, Any], response: str) -> float:
        """Estimate right-hemisphere confidence when no explicit score is returned."""
        if not response:
            return 0.0
        base = float(self.right_config.get("confidence", 0.55))
        if right_context.get("left_response"):
            base += 0.05
        if right_context.get("rag_context"):
            base += 0.05
        if right_context.get("agreement_score", 0.0) >= self.agreement_threshold:
            base += 0.05
        return min(1.0, base)

    def _resolve_right_result(self, prompt: str, right_context: Dict[str, Any], raw_result: Any) -> Dict[str, Any]:
        """Normalize right-hemisphere outputs into a structured result."""
        response = self._extract_text(raw_result, prompt, right_context)
        confidence = self._extract_confidence(raw_result)
        if confidence <= 0.0:
            confidence = self._estimate_right_confidence(right_context, response)
        return {
            "response": response,
            "confidence": confidence,
            "found": bool(response),
            "source": "right_handler",
            "raw_result": raw_result,
        }

    async def _resolve_right_result_async(self, prompt: str, right_context: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve the right hemisphere asynchronously."""
        raw_result = await self._invoke_right_handler(prompt, right_context)
        return self._resolve_right_result(prompt, right_context, raw_result)

    def _resolve_right_result_sync(self, prompt: str, right_context: Dict[str, Any]) -> Dict[str, Any]:
        """Resolve the right hemisphere synchronously."""
        try:
            asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(self._resolve_right_result_async(prompt, right_context))
        response = self._heuristic_right_response(prompt, right_context)
        return self._resolve_right_result(prompt, right_context, response)

    def _arbitrate(self, left_result: Optional[Dict[str, Any]], right_result: Optional[Dict[str, Any]], agreement: float, mode: HemisphereMode) -> Dict[str, Any]:
        """Compute a lightweight arbitration decision for diagnostics."""
        left_conf = float((left_result or {}).get("confidence", 0.0))
        right_conf = float((right_result or {}).get("confidence", 0.0))
        if left_result and right_result:
            if agreement >= self.agreement_threshold:
                primary = "blend"
            elif left_conf >= right_conf:
                primary = "left"
            else:
                primary = "right"
        elif left_result:
            primary = "left"
        elif right_result:
            primary = "right"
        else:
            primary = "none"
        return {
            "mode": mode.value,
            "primary": primary,
            "agreement_score": agreement,
            "left_confidence": left_conf,
            "right_confidence": right_conf,
            "decision": "joint" if left_result and right_result else primary,
        }

    def _record_state(
        self,
        *,
        query: str,
        character_id: Optional[str],
        rag_context: str,
        mode: HemisphereMode,
        left_result: Optional[Dict[str, Any]] = None,
        right_result: Optional[Dict[str, Any]] = None,
        character_context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Records the current processing state into the shared state store.

        Returns:
            A snapshot of the recorded state.
        """
        state = HemisphereState(
            query=query,
            character_id=character_id or "",
            mode=mode.value,
            rag_context=rag_context,
            left_response=(left_result or {}).get("response", ""),
            right_response=(right_result or {}).get("response", ""),
            left_confidence=float((left_result or {}).get("confidence", 0.0)),
            right_confidence=float((right_result or {}).get("confidence", 0.0)),
            left_source=(left_result or {}).get("source", ""),
            right_source=(right_result or {}).get("source", ""),
            agreement_score=float((metadata or {}).get("agreement_score", 0.0)),
            character_context=character_context or {},
            metadata=metadata or {},
            signals=list(self._shared_state.get("signals", [])),
            arbitration=dict(self._shared_state.get("arbitration", {})),
            final_response=str(self._shared_state.get("final_response", "")),
            updated_at=time.time(),
        )
        snapshot = {
            "query": state.query,
            "character_id": state.character_id,
            "mode": state.mode,
            "rag_context": state.rag_context,
            "left_response": state.left_response,
            "right_response": state.right_response,
            "left_confidence": state.left_confidence,
            "right_confidence": state.right_confidence,
            "left_source": state.left_source,
            "right_source": state.right_source,
            "agreement_score": state.agreement_score,
            "character_context": state.character_context,
            "metadata": state.metadata,
            "signals": state.signals,
            "arbitration": state.arbitration,
            "final_response": state.final_response,
            "updated_at": state.updated_at,
        }
        self._shared_state.clear()
        self._shared_state.update(snapshot)
        return snapshot

    def handoff_state(
        self,
        *,
        query: str,
        character_id: Optional[str] = None,
        rag_context: str = "",
        mode: HemisphereMode = HemisphereMode.AUTO,
        left_result: Optional[Dict[str, Any]] = None,
        right_result: Optional[Dict[str, Any]] = None,
        character_context: Optional[Dict[str, Any]] = None,
        metadata: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        """Public wrapper for _record_state."""
        return self._record_state(
            query=query,
            character_id=character_id,
            rag_context=rag_context,
            mode=mode,
            left_result=left_result,
            right_result=right_result,
            character_context=character_context,
            metadata=metadata,
        )

    def _build_right_context(self, prompt: str, state: Dict[str, Any]) -> Dict[str, Any]:
        """Constructs the context dictionary for the right hemisphere handler.

        Args:
            prompt: The input prompt.
            state: The current state snapshot.

        Returns:
            A dictionary containing the combined context.
        """
        context = dict(state)
        context.setdefault("prompt", prompt)
        context.setdefault("query", state.get("query", prompt))
        context.setdefault("character_id", state.get("character_id", ""))
        context.setdefault("rag_context", state.get("rag_context", ""))
        context.setdefault("left_response", state.get("left_response", ""))
        context.setdefault("left_confidence", state.get("left_confidence", 0.0))
        context.setdefault("agreement_score", state.get("agreement_score", 0.0))
        context.setdefault("signals", state.get("signals", []))
        context.setdefault("right_tone", self.right_config.get("tone", "reflective"))
        
        # Inject Deep Social State
        npc_profile = self._social_fabric.get_npc(state.get("character_id", ""))
        if npc_profile:
            context["npc_profile"] = {
                "name": npc_profile.name,
                "traits": npc_profile.personality_traits,
                "tags": list(npc_profile.social_tags),
                "factions": list(npc_profile.faction_ids)
            }
        
        # If we have a target (e.g. player), get disposition
        target_id = state.get("metadata", {}).get("target_id")
        if target_id and state.get("character_id"):
            context["disposition"] = self._social_fabric.get_disposition(
                state["character_id"], target_id
            )
            
        return context

    def _summarize_query(self, query: str) -> str:
        """Summarizes a query into a short phrase for heuristic output."""
        tokens = [token for token in query.lower().replace("?", " ").split() if len(token) > 3]
        if not tokens:
            return "the request"
        return ", ".join(tokens[:4])

    def _heuristic_right_response(self, prompt: str, right_context: Dict[str, Any]) -> str:
        """Generates a rule-based response if no right handler is available."""
        query = right_context.get("query", prompt)
        left_response = (right_context.get("left_response") or "").strip()
        rag_context = (right_context.get("rag_context") or "").strip()
        persona = self.right_config.get("persona_name") or right_context.get("character_id") or "right hemisphere"
        disposition = right_context.get("disposition", 0.0)
        query_focus = self._summarize_query(query)

        # Disposition-aware tone selection
        if disposition > 0.5:
            opener = f"[{persona}] I'm glad you asked about {query_focus}."
            bridge = "It's a pleasure to share this with you."
        elif disposition < -0.3:
            opener = f"[{persona}] You again? Fine, about {query_focus}..."
            bridge = "Don't expect much more from me."
        else:
            opener = f"[{persona}] Regarding {query_focus}."
            bridge = "The broader context suggests a more human read is needed."

        parts = [opener, bridge]
        
        if rag_context:
            first_line = rag_context.splitlines()[0].strip()
            if first_line:
                parts.append(f"My sources say: {first_line[:160]}")
        if left_response:
            # If they like the player, they elaborate on the analytical core
            if disposition > 0.2:
                parts.append(f"To be precise, as my analysis shows: {left_response[:160]}")
            else:
                parts.append(f"Analytical anchor: {left_response[:160]}")
        
        if disposition > 0.6:
            parts.append("I hope that's exactly what you were looking for.")
        elif disposition < -0.5:
            parts.append("That's all I'm giving you.")
        else:
            parts.append("It's the most complete view I have right now.")
            
        return " ".join(parts)

    def _extract_text(self, result: Any, prompt: str, right_context: Dict[str, Any]) -> str:
        """Extracts response text from various handler output formats."""
        if result is None:
            return self._heuristic_right_response(prompt, right_context)
        if isinstance(result, str):
            return result
        if isinstance(result, dict):
            for key in ("response", "answer", "final_response", "text", "output"):
                value = result.get(key)
                if isinstance(value, str) and value.strip():
                    return value
            nested = result.get("result")
            if isinstance(nested, str) and nested.strip():
                return nested
            if hasattr(result, "get"):
                try:
                    value = result.get("response")
                    if isinstance(value, str) and value.strip():
                        return value
                except Exception:
                    pass
        for attr in ("response", "answer", "final_response", "text", "output"):
            value = getattr(result, attr, None)
            if isinstance(value, str) and value.strip():
                return value
        return str(result)

    def _extract_confidence(self, result: Any) -> float:
        """Extracts confidence score from handler output."""
        if isinstance(result, dict):
            for key in ("confidence", "raw_confidence", "score"):
                value = result.get(key)
                if isinstance(value, (int, float)):
                    return float(value)
        for attr in ("confidence", "raw_confidence", "score"):
            value = getattr(result, attr, None)
            if isinstance(value, (int, float)):
                return float(value)
        return 0.0

    async def _invoke_right_handler(self, prompt: str, right_context: Dict[str, Any]) -> Any:
        """Invokes the configured right hemisphere handler and returns the raw result."""
        handler = self._right_handler
        if handler is None:
            return self._heuristic_right_response(prompt, right_context)

        candidates: list[Callable[[], Any]] = []
        if callable(handler):
            candidates.extend(
                [
                    lambda: handler(prompt, right_context),
                    lambda: handler(prompt, right_context=right_context),
                    lambda: handler(prompt),
                ]
            )
        else:
            for name in ("process_query", "process", "think", "respond"):
                method = getattr(handler, name, None)
                if method is not None:
                    candidates.extend(
                        [
                            lambda method=method: method(prompt, right_context),
                            lambda method=method: method(prompt, right_context=right_context),
                            lambda method=method: method(prompt),
                        ]
                    )
                    break

        for candidate in candidates:
            try:
                result = candidate()
                if inspect.isawaitable(result):
                    result = await result
                return result
            except TypeError:
                continue
            except Exception as exc:
                logger.warning("Right handler failed (%s); falling back to heuristic output.", exc)
                break

        return self._heuristic_right_response(prompt, right_context)

    def _right_response_sync(self, prompt: str, right_context: Dict[str, Any]) -> str:
        """Synchronous wrapper for _invoke_right_handler."""
        return self._resolve_right_result_sync(prompt, right_context)["response"]

    def left(self, prompt: str, character_id: Optional[str] = None, rag_context: str = "") -> str:
        """Executes a left-hemisphere (analytical) reasoning pass.

        Args:
            prompt: The input query or prompt.
            character_id: Optional character ID. Defaults to None.
            rag_context: Optional RAG context. Defaults to "".

        Returns:
            The left-hemisphere response string.
        """
        result = self._query_kernel(prompt, character_id, rag_context)
        signal = self._emit_signal(
            "left",
            "right",
            "handoff",
            {
                "query": prompt,
                "character_id": character_id or "",
                "response": result.get("response", ""),
                "confidence": float(result.get("confidence", 0.0)),
                "module_used": result.get("module_used", ""),
                "source": result.get("source", ""),
                "rag_context": rag_context,
            },
        )
        self._record_state(
            query=prompt,
            character_id=character_id,
            rag_context=rag_context,
            mode=HemisphereMode.LEFT,
            left_result=result,
            metadata={
                "left_source": result.get("source", ""),
                "left_module": result.get("module_used", ""),
                "left_signal_id": signal["signal_id"],
            },
        )
        return result.get("response", "")

    def right(self, prompt: str) -> str:
        """Executes a right-hemisphere (intuitive) reasoning pass.

        Args:
            prompt: The input query or prompt.

        Returns:
            The right-hemisphere response string.
        """
        state = self._build_right_context(prompt, dict(self._shared_state))
        result = self._resolve_right_result_sync(prompt, state)
        signal = self._emit_signal(
            "right",
            "left",
            "response",
            {
                "query": state.get("query", prompt),
                "character_id": state.get("character_id", ""),
                "response": result["response"],
                "confidence": result["confidence"],
                "agreement_score": state.get("agreement_score", 0.0),
            },
        )
        self._record_state(
            query=state.get("query", prompt),
            character_id=state.get("character_id", ""),
            rag_context=state.get("rag_context", ""),
            mode=HemisphereMode.RIGHT,
            right_result=result,
            metadata={"right_source": "right_handler", "right_signal_id": signal["signal_id"]},
        )
        return result["response"]

    def _calculate_agreement(self, left_resp: str, right_resp: str) -> float:
        """Calculates token-based overlap between two responses.

        Returns:
            A Jaccard similarity score [0.0, 1.0].
        """
        if not left_resp or not right_resp:
            return 0.0
        left_tokens = set(left_resp.lower().split())
        right_tokens = set(right_resp.lower().split())
        if not left_tokens or not right_tokens:
            return 0.0
        return len(left_tokens & right_tokens) / len(left_tokens | right_tokens)

    def synthesize(self, left_out: str, right_out: str) -> str:
        """Merges outputs from both hemispheres into a single response.

        Args:
            left_out: Response from the left hemisphere.
            right_out: Response from the right hemisphere.

        Returns:
            A synthesized response string.
        """
        if not left_out and not right_out:
            return ""
        if not left_out:
            return right_out
        if not right_out:
            return left_out

        agreement = self._calculate_agreement(left_out, right_out)
        right_clean = right_out.replace("[right] ", "", 1).strip()
        left_clean = left_out.strip()
        if agreement >= self.agreement_threshold:
            return left_clean if len(left_clean) >= len(right_clean) else right_clean

        if left_clean == right_clean:
            return left_clean
        return f"{left_clean} | Contextually, {right_clean}"

    async def _resolve_right_async(self, prompt: str, right_context: Dict[str, Any]) -> str:
        """Internal async helper for right hemisphere resolution."""
        result = await self._resolve_right_result_async(prompt, right_context)
        return result["response"]

    def _build_parallel_seed(
        self,
        query: str,
        character_id: Optional[str],
        rag_context: str,
        mode: HemisphereMode,
        character_context: Optional[Dict[str, Any]],
        max_tokens: int,
    ) -> Dict[str, Any]:
        """Build a frozen snapshot for concurrent hemisphere execution."""
        return {
            "query": query,
            "character_id": character_id or "",
            "mode": mode.value,
            "rag_context": rag_context,
            "left_response": "",
            "right_response": "",
            "left_confidence": 0.0,
            "right_confidence": 0.0,
            "left_source": "",
            "right_source": "",
            "agreement_score": 0.0,
            "character_context": character_context or {},
            "metadata": {"max_tokens": max_tokens},
            "signals": list(self._shared_state.get("signals", [])),
            "arbitration": {},
            "final_response": "",
            "updated_at": time.time(),
        }

    def _emit_result_signals(
        self,
        query: str,
        character_id: Optional[str],
        rag_context: str,
        left_result: Optional[Dict[str, Any]],
        right_result: Optional[Dict[str, Any]],
        max_tokens: int,
    ) -> None:
        """Emit post-inference signal records for both hemispheres."""
        if left_result:
            self._emit_signal(
                "left",
                "right",
                "handoff",
                {
                    "query": query,
                    "character_id": character_id or "",
                    "response": left_result.get("response", ""),
                    "confidence": float(left_result.get("confidence", 0.0)),
                    "module_used": left_result.get("module_used", ""),
                    "source": left_result.get("source", ""),
                    "rag_context": rag_context,
                    "max_tokens": max_tokens,
                },
            )
        if right_result:
            self._emit_signal(
                "right",
                "left",
                "response",
                {
                    "query": query,
                    "character_id": character_id or "",
                    "response": right_result.get("response", ""),
                    "confidence": float(right_result.get("confidence", 0.0)),
                    "agreement_score": float(right_result.get("agreement_score", 0.0)),
                },
            )

    async def route_query(
        self,
        query: str,
        hemisphere: str = "auto",
        character_context: Optional[Dict] = None,
        rag_context: str = "",
        max_tokens: int = 512,
    ) -> Dict[str, Any]:
        """Top-level entry point for routing a query through the dual-hemisphere system.

        Args:
            query: The user query string.
            hemisphere: Routing mode ("left", "right", "both", "auto"). Defaults to "auto".
            character_context: Optional metadata about the character. Defaults to None.
            rag_context: Optional RAG context string. Defaults to "".
            max_tokens: Maximum tokens for output. Defaults to 512.

        Returns:
            A dictionary containing the response, metrics, and state snapshots.
        """
        self._queries_total += 1
        start = time.time()
        mode = self._normalize_mode(hemisphere)
        character_id = character_context.get("character_id") if character_context else None

        left_result: Optional[Dict[str, Any]] = None
        right_result: Optional[Dict[str, Any]] = None
        arbitration: Dict[str, Any] = {"mode": mode.value, "primary": "none"}
        parallel_seed = self._build_parallel_seed(
            query=query,
            character_id=character_id,
            rag_context=rag_context,
            mode=mode,
            character_context=character_context,
            max_tokens=max_tokens,
        )

        if mode == HemisphereMode.LEFT:
            left_result = self._query_kernel(query, character_id, rag_context)
            arbitration = self._arbitrate(left_result, None, 0.0, mode)
            self._emit_result_signals(query, character_id, rag_context, left_result, None, max_tokens)
            snapshot = self.handoff_state(
                query=query,
                character_id=character_id,
                rag_context=rag_context,
                mode=mode,
                left_result=left_result,
                right_result=None,
                character_context=character_context,
                metadata={"max_tokens": max_tokens, "arbitration": arbitration},
            )
            self._left_wins += 1
            return {
                "response": left_result.get("response", "") if left_result else "",
                "hemisphere_used": "left",
                "raw_confidence": float(left_result.get("confidence", 0.0)) if left_result else 0.0,
                "agreement_score": None,
                "left_response": left_result.get("response", "") if left_result else None,
                "right_response": None,
                "latency_ms": (time.time() - start) * 1000,
                "state_handoff": snapshot,
            }

        if mode == HemisphereMode.RIGHT:
            right_context = self._build_right_context(query, parallel_seed)
            right_result = await self._resolve_right_result_async(query, right_context)
            arbitration = self._arbitrate(None, right_result, 0.0, mode)
            self._emit_result_signals(query, character_id, rag_context, None, right_result, max_tokens)
            snapshot = self.handoff_state(
                query=query,
                character_id=character_id,
                rag_context=rag_context,
                mode=mode,
                left_result=None,
                right_result=right_result,
                character_context=character_context,
                metadata={"max_tokens": max_tokens, "arbitration": arbitration},
            )
            self._right_wins += 1
            return {
                "response": right_result["response"],
                "hemisphere_used": "right",
                "raw_confidence": float(right_result.get("confidence", 0.0)),
                "agreement_score": None,
                "left_response": None,
                "right_response": right_result.get("response", ""),
                "latency_ms": (time.time() - start) * 1000,
                "state_handoff": snapshot,
            }

        if mode in (HemisphereMode.BOTH, HemisphereMode.AUTO):
            right_context = self._build_right_context(query, parallel_seed)
            left_task = asyncio.to_thread(self._query_kernel, query, character_id, rag_context)
            right_task = self._resolve_right_result_async(query, right_context)
            left_raw, right_raw = await asyncio.gather(left_task, right_task, return_exceptions=True)

            if isinstance(left_raw, Exception):
                logger.warning("Parallel left hemisphere failed (%s); using Python fallback.", left_raw)
                left_result = self._query_python_left(query, character_id, rag_context)
            else:
                left_result = left_raw

            if isinstance(right_raw, Exception):
                logger.warning("Parallel right hemisphere failed (%s); using heuristic fallback.", right_raw)
                right_result = self._resolve_right_result(
                    query,
                    right_context,
                    self._heuristic_right_response(query, right_context),
                )
            else:
                right_result = right_raw

            agreement = self._calculate_agreement(
                left_result.get("response", "") if left_result else "",
                right_result.get("response", "") if right_result else "",
            )
            arbitration = self._arbitrate(left_result, right_result, agreement, mode)
            raw_confidence = max(
                float(left_result.get("confidence", 0.0)) if left_result else 0.0,
                float(right_result.get("confidence", 0.0)) if right_result else 0.0,
            )
            if agreement >= self.agreement_threshold:
                raw_confidence = min(1.0, raw_confidence + 0.05)

            self._left_wins += 1
            self._right_wins += 1
            self._agreement_count += 1
            self._agreement_sum += agreement
            self._emit_result_signals(query, character_id, rag_context, left_result, right_result, max_tokens)

            if mode == HemisphereMode.AUTO:
                if left_result and float(left_result.get("confidence", 0.0)) >= self.agreement_threshold:
                    snapshot = self.handoff_state(
                        query=query,
                        character_id=character_id,
                        rag_context=rag_context,
                        mode=mode,
                        left_result=left_result,
                        right_result=right_result,
                        character_context=character_context,
                        metadata={"max_tokens": max_tokens, "agreement_score": agreement, "arbitration": arbitration},
                    )
                    return {
                        "response": left_result.get("response", ""),
                        "hemisphere_used": "left",
                        "raw_confidence": float(left_result.get("confidence", 0.0)),
                        "agreement_score": agreement,
                        "left_response": left_result.get("response", ""),
                        "right_response": right_result.get("response", ""),
                        "latency_ms": (time.time() - start) * 1000,
                        "state_handoff": snapshot,
                    }
                snapshot = self.handoff_state(
                    query=query,
                    character_id=character_id,
                    rag_context=rag_context,
                    mode=mode,
                    left_result=left_result,
                    right_result=right_result,
                    character_context=character_context,
                    metadata={"max_tokens": max_tokens, "agreement_score": agreement, "arbitration": arbitration},
                )
                return {
                    "response": right_result.get("response", ""),
                    "hemisphere_used": "right",
                    "raw_confidence": float(right_result.get("confidence", 0.0)),
                    "agreement_score": agreement,
                    "left_response": left_result.get("response", ""),
                    "right_response": right_result.get("response", ""),
                    "latency_ms": (time.time() - start) * 1000,
                    "state_handoff": snapshot,
                }

            final_response = self.synthesize(
                left_result.get("response", "") if left_result else "",
                right_result.get("response", "") if right_result else "",
            )
            snapshot = self.handoff_state(
                query=query,
                character_id=character_id,
                rag_context=rag_context,
                mode=mode,
                left_result=left_result,
                right_result=right_result,
                character_context=character_context,
                metadata={
                    "max_tokens": max_tokens,
                    "agreement_score": agreement,
                    "arbitration": arbitration,
                    "final_response": final_response,
                },
            )
            self._shared_state["arbitration"] = arbitration
            self._shared_state["final_response"] = final_response
            return {
                "response": final_response,
                "hemisphere_used": "both",
                "raw_confidence": raw_confidence,
                "agreement_score": agreement,
                "left_response": left_result.get("response", "") if left_result else None,
                "right_response": right_result.get("response", ""),
                "left_confidence": float(left_result.get("confidence", 0.0)) if left_result else 0.0,
                "right_confidence": float(right_result.get("confidence", 0.0)) if right_result else 0.0,
                "latency_ms": (time.time() - start) * 1000,
                "state_handoff": snapshot,
            }

        return {
            "response": "",
            "hemisphere_used": "none",
            "raw_confidence": 0.0,
            "agreement_score": None,
            "left_response": None,
            "right_response": None,
            "latency_ms": (time.time() - start) * 1000,
            "state_handoff": self.handoff_state(
                query=query,
                character_id=character_id,
                rag_context=rag_context,
                mode=mode,
                left_result=None,
                right_result=None,
                character_context=character_context,
                metadata={"max_tokens": max_tokens, "arbitration": arbitration},
            ),
        }

    def _normalize_mode(self, hemisphere: Any) -> HemisphereMode:
        """Normalizes various hemisphere mode inputs into a HemisphereMode enum."""
        if isinstance(hemisphere, HemisphereMode):
            return hemisphere
        value = str(hemisphere or "auto").strip().lower()
        try:
            return HemisphereMode(value)
        except ValueError:
            return HemisphereMode.AUTO

    def get_kernel_stats(self) -> Dict[str, Any]:
        """Returns runtime statistics for the bridge and kernel.

        Returns:
            A dictionary containing win rates, agreement scores, and status.
        """
        avg_agreement = self._agreement_sum / self._agreement_count if self._agreement_count > 0 else 0.0
        return {
            "kernel_alive": self.ping_kernel(),
            "queries_total": self._queries_total,
            "left_wins": self._left_wins,
            "right_wins": self._right_wins,
            "avg_agreement_score": round(avg_agreement, 4),
            "agreement_threshold": self.agreement_threshold,
            "last_mode": self._shared_state.get("mode"),
            "last_character_id": self._shared_state.get("character_id"),
            "last_left_source": self._shared_state.get("left_source"),
            "last_right_source": self._shared_state.get("right_source"),
            "last_agreement_score": self._shared_state.get("agreement_score", 0.0),
            "signal_count": len(self._shared_state.get("signals", [])),
            "last_arbitration": self._shared_state.get("arbitration", {}),
            "last_final_response": self._shared_state.get("final_response", ""),
        }

    def stop(self) -> None:
        """Gracefully stops the kernel process."""
        if self._kernel_proc:
            logger.info("Stopping kernel process...")
            self._kernel_proc.terminate()
            try:
                self._kernel_proc.wait(timeout=5)
            except subprocess.TimeoutExpired:
                self._kernel_proc.kill()
            self._kernel_proc = None

    def __del__(self):
        self.stop()
