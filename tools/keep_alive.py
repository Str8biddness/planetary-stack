import subprocess
import time
import sys
import os
import signal
import logging
from pathlib import Path

# Configuration
PROJ_ROOT = Path(__file__).resolve().parent.parent
VENV_PYTHON = PROJ_ROOT / ".venv" / "Scripts" / "python.exe"
SERVER_SCRIPT = PROJ_ROOT / "api" / "production_server.py"
LOG_FILE = PROJ_ROOT / "data" / "pipeline.log"
PORT = 5000
SUBDOMAIN = "nine-melons-cheat"

# Setup Logging
LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[
        logging.FileHandler(LOG_FILE),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger("supervisor")

class PipelineSupervisor:
    def __init__(self):
        self.server_proc = None
        self.tunnel_proc = None
        self.running = True

    def cleanup_port(self):
        """Kill any process existing on the target port."""
        try:
            cmd = f"netstat -ano | findstr :{PORT}"
            output = subprocess.check_output(cmd, shell=True).decode()
            pids = set()
            for line in output.strip().split("\n"):
                parts = line.split()
                if len(parts) > 4:
                    pids.add(parts[-1])
            
            for pid in pids:
                logger.info(f"Cleaning up existing process {pid} on port {PORT}")
                subprocess.run(f"taskkill /F /PID {pid}", shell=True, capture_output=True)
        except subprocess.CalledProcessError:
            pass # Port is likely free

    def start_server(self):
        logger.info("Starting Synthesus Server...")
        self.server_proc = subprocess.Popen(
            [str(VENV_PYTHON), str(SERVER_SCRIPT)],
            cwd=str(PROJ_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

    def start_tunnel(self):
        logger.info(f"Starting Localtunnel (subdomain: {SUBDOMAIN})...")
        # Using npx directly
        self.tunnel_proc = subprocess.Popen(
            ["npx.cmd", "localtunnel", "--port", str(PORT), "--subdomain", SUBDOMAIN],
            cwd=str(PROJ_ROOT),
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=True
        )

    def stop(self, *args):
        logger.info("Stopping supervisor...")
        self.running = False
        if self.server_proc:
            self.server_proc.terminate()
        if self.tunnel_proc:
            self.tunnel_proc.terminate()
        sys.exit(0)

    def run(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        self.cleanup_port()
        
        while self.running:
            # Check Server
            if self.server_proc is None or self.server_proc.poll() is not None:
                if self.server_proc:
                    logger.warning(f"Server exited with code {self.server_proc.returncode}. Restarting...")
                self.start_server()

            # Check Tunnel (simple process check)
            if self.tunnel_proc is None or self.tunnel_proc.poll() is not None:
                if self.tunnel_proc:
                    logger.warning(f"Tunnel exited with code {self.tunnel_proc.returncode}. Restarting...")
                self.start_tunnel()

            time.sleep(10)

if __name__ == "__main__":
    supervisor = PipelineSupervisor()
    supervisor.run()
