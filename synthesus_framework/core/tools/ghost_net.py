import socket
import json
import logging
import threading
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

class GhostNetNode:
    """
    Lightweight, local UDP/TCP P2P node for Ghostkey threat sharing.
    Allows instances to broadcast and receive anomaly signatures (e.g., blocked IPs).
    """
    def __init__(self, port: int = 20260, node_id: str = "ghostkey_primary"):
        self.port = port
        self.node_id = node_id
        self.known_threats: Dict[str, float] = {} # threat_id (e.g., IP) -> timestamp
        self.running = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        # Allow multiple apps to listen on the same port if testing locally
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        if hasattr(socket, "SO_REUSEPORT"):
            self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        self.sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        
        try:
            self.sock.bind(('', self.port))
            self.sock.settimeout(1.0)
        except Exception as e:
            logger.error(f"GhostNet: Failed to bind port {self.port}: {e}")

    def start(self):
        """Starts the listener thread."""
        if self.running:
            return
        self.running = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()
        logger.info(f"GhostNet Node '{self.node_id}' active on UDP {self.port}")

    def stop(self):
        self.running = False
        if hasattr(self, 'listener_thread'):
            self.listener_thread.join(timeout=2.0)
        self.sock.close()

    def broadcast_threat(self, threat_type: str, threat_value: str, severity: str = "high"):
        """Broadcasts a threat to the local subnet."""
        if not self.running:
            return
            
        message = {
            "version": "1.0",
            "sender_id": self.node_id,
            "type": "threat_alert",
            "data": {
                "threat_type": threat_type, # e.g., "malicious_ip", "unauthorized_port"
                "threat_value": threat_value,
                "severity": severity,
                "timestamp": time.time()
            }
        }
        
        try:
            payload = json.dumps(message).encode('utf-8')
            # 255.255.255.255 is the local broadcast address
            self.sock.sendto(payload, ('<broadcast>', self.port))
            # Track it locally so we don't echo it back
            threat_key = f"{threat_type}:{threat_value}"
            self.known_threats[threat_key] = time.time()
            logger.info(f"GhostNet: Broadcasted threat {threat_key}")
        except Exception as e:
            logger.error(f"GhostNet broadcast failed: {e}")

    def _listen_loop(self):
        """Listens for incoming UDP broadcasts."""
        while self.running:
            try:
                data, addr = self.sock.recvfrom(4096)
                message = json.loads(data.decode('utf-8'))
                
                # Ignore our own messages
                if message.get("sender_id") == self.node_id:
                    continue
                    
                if message.get("type") == "threat_alert":
                    threat_data = message.get("data", {})
                    threat_type = threat_data.get("threat_type")
                    threat_value = threat_data.get("threat_value")
                    
                    threat_key = f"{threat_type}:{threat_value}"
                    
                    # If it's a new threat we haven't seen in the last hour
                    if threat_key not in self.known_threats or (time.time() - self.known_threats[threat_key] > 3600):
                        self.known_threats[threat_key] = time.time()
                        logger.warning(f"GhostNet [Incoming Alert from {message['sender_id']}]: {threat_key}")
                        # In a fully integrated system, we would inject this into FluidState as a new hypothesis
                        
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"GhostNet listen error: {e}")

    def get_recent_external_threats(self) -> List[str]:
        """Returns a list of threat descriptions received recently."""
        # Cleanup old threats (older than 1 hour)
        current_time = time.time()
        self.known_threats = {k: v for k, v in self.known_threats.items() if current_time - v < 3600}
        
        return list(self.known_threats.keys())
