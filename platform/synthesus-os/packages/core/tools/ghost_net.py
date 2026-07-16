import socket
import json
import logging
import threading
import time
from typing import Dict, Any, List

logger = logging.getLogger(__name__)

import hmac
import hashlib

class GhostNetNode:
    """
    Secure, local UDP/TCP P2P node for Ghostkey threat sharing.
    Uses HMAC-SHA256 signing to prevent agent impersonation and message tampering.
    """
    def __init__(self, port: int = 20260, node_id: str = "ghostkey_primary", secret_key: str = "GHOSTKEY_INSECURE_DEFAULT"):
        self.port = port
        self.node_id = node_id
        self.secret_key = secret_key.encode('utf-8')
        self.known_threats: Dict[str, Dict[str, Any]] = {} 
        self.peers: Dict[str, Dict[str, Any]] = {} 
        self.incidents: List[Dict[str, Any]] = [] 
        self.running = False
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        
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
        """Starts the listener thread and heartbeat."""
        if self.running:
            return
        self.running = True
        self.listener_thread = threading.Thread(target=self._listen_loop, daemon=True)
        self.listener_thread.start()
        
        self.heartbeat_thread = threading.Thread(target=self._heartbeat_loop, daemon=True)
        self.heartbeat_thread.start()
        
        logger.info(f"GhostNet Node '{self.node_id}' active and SECURED on UDP {self.port}")

    def stop(self):
        self.running = False
        self.sock.close()

    def _sign_message(self, message: Dict[str, Any]) -> str:
        """Generate an HMAC signature for the message body."""
        msg_str = json.dumps(message, sort_keys=True)
        return hmac.new(self.secret_key, msg_str.encode('utf-8'), hashlib.sha256).hexdigest()

    def _verify_signature(self, message: Dict[str, Any], signature: str) -> bool:
        """Verify that the message signature matches the body."""
        expected = self._sign_message(message)
        return hmac.compare_digest(expected, signature)

    def _broadcast(self, data: Dict[str, Any], msg_type: str):
        if not self.running: return
        
        body = {
            "version": "1.2",
            "sender_id": self.node_id,
            "type": msg_type,
            "data": data,
            "timestamp": time.time()
        }
        
        envelope = {
            "body": body,
            "signature": self._sign_message(body)
        }
        
        try:
            payload = json.dumps(envelope).encode('utf-8')
            self.sock.sendto(payload, ('<broadcast>', self.port))
        except Exception as e:
            logger.error(f"GhostNet broadcast failed: {e}")

    def broadcast_incident(self, incident: Dict[str, Any]):
        self._broadcast(incident, "incident_sync")

    def broadcast_threat(self, threat_type: str, threat_value: str, severity: str = "high"):
        self._broadcast({
            "threat_type": threat_type,
            "threat_value": threat_value,
            "severity": severity
        }, "threat_alert")

    def _heartbeat_loop(self):
        while self.running:
            self._broadcast({"status": "active"}, "peer_alive")
            now = time.time()
            self.peers = {k: v for k, v in self.peers.items() if now - v.get('last_seen', 0) < 30}
            time.sleep(10)

    def _listen_loop(self):
        while self.running:
            try:
                data, addr = self.sock.recvfrom(16384)
                envelope = json.loads(data.decode('utf-8'))
                
                body = envelope.get("body")
                signature = envelope.get("signature")
                
                if not body or not signature:
                    continue
                
                # SECURITY: Verify message came from a trusted agent with the same secret
                if not self._verify_signature(body, signature):
                    logger.warning(f"GhostNet [SECURITY]: Dropped unsigned/invalid message from {addr[0]}")
                    continue
                
                if body.get("sender_id") == self.node_id:
                    continue
                
                msg_type = body.get("type")
                sender_id = body.get("sender_id")
                
                if msg_type == "peer_alive":
                    self.peers[sender_id] = {
                        "last_seen": time.time(),
                        "addr": addr[0],
                        "status": "authenticated"
                    }
                elif msg_type == "threat_alert":
                    threat_data = body.get("data", {})
                    threat_key = f"{threat_data.get('threat_type')}:{threat_data.get('threat_value')}"
                    self.known_threats[threat_key] = threat_data
                    logger.warning(f"GhostNet [SECURE Threat from {sender_id}]: {threat_key}")
                elif msg_type == "incident_sync":
                    incident = body.get("data", {})
                    self.incidents.append(incident)
                    logger.warning(f"GhostNet [SECURE Incident from {sender_id}]: {incident.get('id')}")
                        
            except socket.timeout:
                continue
            except Exception as e:
                logger.debug(f"GhostNet listen error: {e}")

    def get_peers(self) -> List[Dict[str, Any]]:
        return [{"id": k, **v} for k, v in self.peers.items()]

    def get_recent_external_threats(self) -> List[str]:
        return list(self.known_threats.keys())
