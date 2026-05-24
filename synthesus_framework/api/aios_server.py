#!/usr/bin/env python3
"""
Synthesus AIOS Server
AIVM LLC - Hardware-Aware Synthetic Intelligence

Exposes the V3 SynthRuntime and AIOS Hardware Layer to the Synthesus IDE.
"""

import logging
import os
import sys
import time
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import FastAPI, HTTPException, Request, Depends, Header
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

# Add project root to sys.path
PROJ_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJ_ROOT))

from core.synth_runtime import get_runtime

# Setup logging
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(name)s] %(message)s")
logger = logging.getLogger("synthesus.aios")

app = FastAPI(
    title="Synthesus AIOS Server",
    description="V3 Hardware-Aware Synthetic Intelligence Engine",
    version="3.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Admin key for IDE access
ADMIN_KEY = os.environ.get("SYNTHESUS_API_KEY", "sk-synth-dev-key")

# Request Models
class RespondRequest(BaseModel):
    character_id: str = "synth"
    user_input: str
    context: Optional[str] = None
    session_id: Optional[str] = None

class VpdMapRequest(BaseModel):
    parameter_id: str

async def verify_auth(x_api_key: Optional[str] = Header(None)):
    if x_api_key != ADMIN_KEY:
        # In dev mode, we might allow it if no key is provided
        if not x_api_key and os.environ.get("ENV") == "development":
            return
        raise HTTPException(status_code=401, detail="Invalid API Key")

@app.get("/api/health")
async def health():
    runtime = get_runtime()
    return {
        "status": "operational",
        "version": "3.0.0",
        "hardware_aware": bool(runtime._host_profile),
        "vpd_active": bool(runtime._emul_engine and runtime._emul_engine.mapped_parameter_count > 0)
    }

@app.get("/api/hardware/profile")
async def get_hardware_profile(auth=Depends(verify_auth)):
    """Expose the AIOS hardware profile"""
    runtime = get_runtime()
    return runtime._host_profile

@app.post("/api/kernel/vpd/map")
async def map_vpd_parameter(req: VpdMapRequest, auth=Depends(verify_auth)):
    """Map a parameter into the AIOS VPD"""
    runtime = get_runtime()
    if not runtime._emul_engine:
        raise HTTPException(503, "EmulEngine not initialized")
    
    try:
        success = runtime._emul_engine.map_parameter(req.parameter_id)
        return {"success": success, "mapped_count": runtime._emul_engine.mapped_parameter_count}
    except Exception as e:
        logger.error(f"VPD mapping error: {e}")
        raise HTTPException(500, str(e))

import threading

# ... existing imports ...

# Global background VMM state
_vmm_thread = None
_vmm_running = False

@app.post("/api/kernel/vmm/run")
async def run_vmm(auth=Depends(verify_auth)):
    """Start the VMM in a background thread for interactive console use."""
    global _vmm_thread, _vmm_running
    runtime = get_runtime()
    if not runtime._emul_engine:
        raise HTTPException(503, "EmulEngine not initialized")
    
    if _vmm_running:
        return {"status": "already_running"}

    # Perform pre-run setup (AIOS Methodology)
    try:
        if not runtime._emul_engine.initialize():
             raise Exception("EmulEngine initialization failed")
        
        # Map world lore as a test parameter for the VPD
        runtime._emul_engine.map_parameter("lore/world_core")
    except Exception as e:
        logger.error(f"VMM pre-run setup failed: {e}")
        raise HTTPException(500, f"VMM setup failed: {str(e)}")

    def _vmm_worker():
        global _vmm_running
        _vmm_running = True
        try:
            logger.info("VMM background session started")
            # This now runs with the GIL released, allowing console interaction
            runtime._emul_engine.run_abstraction()
        except Exception as e:
            logger.error(f"VMM execution failed: {e}")
        finally:
            _vmm_running = False
            logger.info("VMM background session ended")

    _vmm_thread = threading.Thread(target=_vmm_worker, daemon=True)
    _vmm_thread.start()
    return {"status": "started"}

@app.get("/api/kernel/vmm/console")
async def read_vmm_console(auth=Depends(verify_auth)):
    """Read new output from the guest serial console."""
    runtime = get_runtime()
    if not runtime._emul_engine:
        return {"output": ""}
    return {"output": runtime._emul_engine.read_console_output()}

@app.post("/api/kernel/vmm/console")
async def write_vmm_console(req: Dict[str, str], auth=Depends(verify_auth)):
    """Write input characters to the guest serial console."""
    input_text = req.get("input", "")
    runtime = get_runtime()
    if runtime._emul_engine:
        runtime._emul_engine.write_console_input(input_text)
    return {"success": True}

@app.get("/api/kernel/vpd/dump")
async def dump_vpd(auth=Depends(verify_auth)):
    """Return the AIOS VPD register block and selected parameter bytes."""
    runtime = get_runtime()
    if not runtime._emul_engine:
        raise HTTPException(503, "EmulEngine not initialized")
    return runtime._emul_engine.dump_vpd()

@app.get("/api/kernel/vqd/dump")
async def dump_vqd(auth=Depends(verify_auth)):
    """Return the AIOS VQD register block and simulator status."""
    runtime = get_runtime()
    if not hasattr(runtime, "_vqd") or not runtime._vqd:
        raise HTTPException(503, "VQD not initialized")
    return runtime._vqd.dump()

@app.get("/api/kernel/vnd/dump")
async def dump_vnd(auth=Depends(verify_auth)):
    """Return the AIOS VND register block and search status."""
    runtime = get_runtime()
    if not runtime._emul_engine:
        raise HTTPException(503, "EmulEngine not initialized")
    return runtime._emul_engine.dump_vnd()

@app.get("/api/kernel/vmd/dump")
async def dump_vmd(auth=Depends(verify_auth)):
    """Return the AIOS VMD register block and sync status."""
    runtime = get_runtime()
    if not runtime._emul_engine:
        raise HTTPException(503, "EmulEngine not initialized")
    return runtime._emul_engine.dump_vmd()

@app.get("/api/kernel/vvpu/dump")
async def dump_vvpu(auth=Depends(verify_auth)):
    """Return the AIOS VVPU register block and swarm status."""
    runtime = get_runtime()
    if not runtime._emul_engine:
        raise HTTPException(503, "EmulEngine not initialized")
    return runtime._emul_engine.dump_vvpu()

@app.get("/api/kernel/vsllm/dump")
async def dump_vsllm(auth=Depends(verify_auth)):
    """Return the AIOS VSLLM register block and model status."""
    runtime = get_runtime()
    if not runtime._emul_engine:
        raise HTTPException(503, "EmulEngine not initialized")
    return runtime._emul_engine.dump_sllm()

@app.post("/api/system/freeze")
async def freeze_system(auth=Depends(verify_auth)):
    """Trigger the Manifestation Engine to generate a bootable ISO."""
    runtime = get_runtime()
    if not hasattr(runtime, "_manifestation") or not runtime._manifestation:
        raise HTTPException(503, "Manifestation Engine not initialized")
    asyncio.create_task(runtime._manifestation.freeze_system())
    return {"status": "started"}

@app.get("/api/system/freeze/status")
async def get_freeze_status(auth=Depends(verify_auth)):
    """Return the current progress of the ISO generation."""
    runtime = get_runtime()
    if not hasattr(runtime, "_manifestation") or not runtime._manifestation:
        raise HTTPException(503, "Manifestation Engine not initialized")
    return runtime._manifestation.get_status()

@app.post("/api/respond")
async def respond(req: RespondRequest, auth=Depends(verify_auth)):
    """Main inference endpoint using V3 SynthRuntime"""
    runtime = get_runtime()
    try:
        result = runtime.respond(
            character_id=req.character_id,
            user_input=req.user_input,
            context=req.context,
            session_id=req.session_id
        )
        return {
            "final_response": result.final_response,
            "confidence": result.confidence,
            "module_used": result.module_used,
            "session_id": result.session_id,
            "latency_ms": result.latency_ms
        }
    except Exception as e:
        logger.error(f"Inference error: {e}")
        raise HTTPException(500, str(e))

if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 5000))
    uvicorn.run(app, host="0.0.0.0", port=port)
