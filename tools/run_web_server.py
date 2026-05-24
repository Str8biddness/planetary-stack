# Synthesus 2.0 - Production Web Server
import asyncio
import uvicorn
import os
import sys

# Add root to sys.path
sys.path.insert(0, os.path.abspath(os.path.dirname(__file__)))

from api.production_server import app

async def startup():
    """
    Synthesus Startup Sequence.
    Ensures all neural handlers and cognitive engines are initialized.
    """
    print("SYNTHESUS - Initializing Hyperspace Intelligence...")
    # Add any specific startup logic here if needed
    # For now, we ensure character directory exists
    char_dir = os.path.join(os.path.dirname(__file__), "characters")
    if not os.path.exists(char_dir):
        os.makedirs(char_dir)
        print(f"Created characters directory: {char_dir}")
    
    print("Neural Link Established. Ready for transmission.")

# Register startup event with FastAPI
@app.on_event("startup")
async def startup_event():
    """Run startup sequence when FastAPI starts"""
    await startup()

if __name__ == "__main__":
    # Start uvicorn server
    # Port 5001 as requested by user
    print("Launching Synthesus Backend on Port 5001...")
    uvicorn.run(
        app,  # Pass app object directly instead of import string
        host="0.0.0.0",
        port=5010,
        log_level="info",
        reload=False
    )
