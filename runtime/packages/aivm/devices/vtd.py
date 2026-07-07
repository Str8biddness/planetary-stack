from __future__ import annotations
import hashlib
import logging
from typing import Any, Dict, List, Optional
from .base import Device

logger = logging.getLogger("aivm.devices.vtd")

class VTD(Device):
    """
    Virtual Tool Device (VTD).
    Provides a hardware-abstracted interface for agentic tools.
    Available ONLY to NPCs with AGENT permission level.
    """
    
    def __init__(self, manifestation_engine: Optional[Any] = None, scraper: Optional[Any] = None):
        self._manifestation = manifestation_engine
        self._scraper = scraper
        self._shell_authorized = False

    def execute_tool(self, tool_id: str, params: Dict[str, Any]) -> Any:
        """Execute a host-level tool."""
        if tool_id == "freeze" and self._manifestation:
            logger.info("VTD: Executing system manifestation (FREEZE)...")
            return self._manifestation.freeze_system(**params)
        
        if tool_id == "scrape" and self._scraper:
            logger.info(f"VTD: Executing web ingress (SCRAPE) for query: {params.get('query')}")
            return self._scraper.scrape(**params)

        return {"error": f"Tool {tool_id} not available or authorized."}

    def snapshot(self) -> bytes:
        return b"vtd_snapshot"

    def restore(self, blob: bytes) -> None:
        pass

    def fingerprint(self) -> str:
        return hashlib.sha256(self.snapshot()).hexdigest()
