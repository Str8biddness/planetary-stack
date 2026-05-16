import asyncio
import os
import sys
import logging
from pathlib import Path

# Setup logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("quadbrain_launcher")

# Ensure framework is in path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

async def run_master():
    logger.info("Starting Quadbrain Master...")
    from aios.quadbrain.quadbrain_master import QuadbrainMaster
    master = QuadbrainMaster()
    # In a real cluster, this would start the gRPC or REST interface
    # For now, we simulate a long-running thinking loop
    while True:
        await asyncio.sleep(3600)

async def run_worker(brain_type: str):
    logger.info(f"Starting Quadbrain Worker: {brain_type}...")
    # Logic to handle specific brain roles (Memory, Pattern, Security, Executive)
    while True:
        await asyncio.sleep(3600)

if __name__ == "__main__":
    mode = os.environ.get("SYNT_MODE", "single")
    role = os.environ.get("SYNT_ROLE", "master")
    
    if mode == "quadbrain":
        if role == "master":
            asyncio.run(run_master())
        else:
            asyncio.run(run_worker(role))
    else:
        logger.info("Running in Single Node mode (Synthesus 4.0 Standard)")
        # Import and start the standard production server logic
        from api.production_server import app
        import uvicorn
        uvicorn.run(app, host="0.0.0.0", port=5010)
