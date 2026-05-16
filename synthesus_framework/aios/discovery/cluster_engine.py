import socket
import logging
import time
from zeroconf import IPVersion, ServiceInfo, Zeroconf, ServiceBrowser

from . import grpc_server
from .grpc_client import ClusterClient

logger = logging.getLogger("aios_discovery")

class SynthesusDiscovery:
    """Handles local network discovery and clustering for Synthesus AIOS nodes."""
    
    def __init__(self, node_id: str, rest_port: int = 5010, grpc_port: int = 5051):
        self.node_id = node_id
        self.rest_port = rest_port
        self.grpc_port = grpc_port
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.peers = {}
        self.grpc_clients = {}
        self._grpc_server = None

    def start_grpc(self):
        """Start the gRPC server for this node."""
        self._grpc_server = grpc_server.serve(self.node_id, self.grpc_port)

    def get_local_ip(self):
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            # doesn't even have to be reachable
            s.connect(('10.255.255.255', 1))
            IP = s.getsockname()[0]
        except Exception:
            IP = '127.0.0.1'
        finally:
            s.close()
        return IP

    def advertise(self):
        """Broadcast this node to the local network."""
        local_ip = self.get_local_ip()
        desc = {
            'node_id': self.node_id, 
            'version': '4.0.0',
            'grpc_port': str(self.grpc_port)
        }
        
        info = ServiceInfo(
            "_synthesus._tcp.local.",
            f"{self.node_id}._synthesus._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=self.rest_port,
            properties=desc,
            server=f"{self.node_id}.local.",
        )
        
        logger.info(f"Advertising Synthesus node {self.node_id} at {local_ip}:{self.rest_port} (gRPC: {self.grpc_port})")
        self.zeroconf.register_service(info)

    def browse(self):
        """Start browsing for other Synthesus nodes."""
        browser = ServiceBrowser(self.zeroconf, "_synthesus._tcp.local.", self)
        return browser

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        if name in self.peers:
            node_id = self.peers[name]['node_id']
            logger.info(f"Node {node_id} left the cluster")
            if node_id in self.grpc_clients:
                self.grpc_clients[node_id].close()
                del self.grpc_clients[node_id]
            del self.peers[name]

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            address = socket.inet_ntoa(info.addresses[0])
            node_id = info.properties.get(b'node_id', b'unknown').decode()
            g_port = int(info.properties.get(b'grpc_port', b'5051').decode())
            
            self.peers[name] = {
                'ip': address, 
                'port': info.port, 
                'grpc_port': g_port,
                'node_id': node_id
            }
            
            # Connect gRPC client
            target = f"{address}:{g_port}"
            self.grpc_clients[node_id] = ClusterClient(target)
            
            logger.info(f"Connected to peer node: {node_id} at {address} (REST: {info.port}, gRPC: {g_port})")

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def stop(self):
        self.zeroconf.unregister_all_services()
        self.zeroconf.close()
        if self._grpc_server:
            self._grpc_server.stop(0)

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    node_name = socket.gethostname()
    discovery = SynthesusDiscovery(node_id=node_name)
    discovery.start_grpc()
    discovery.advertise()
    discovery.browse()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        discovery.stop()
