import socket
import logging
import time
from zeroconf import IPVersion, ServiceInfo, Zeroconf, ServiceBrowser

logger = logging.getLogger("aios_discovery")

class SynthesusDiscovery:
    """Handles local network discovery and clustering for Synthesus AIOS nodes."""
    
    def __init__(self, node_id: str, port: int = 5010):
        self.node_id = node_id
        self.port = port
        self.zeroconf = Zeroconf(ip_version=IPVersion.V4Only)
        self.peers = {}

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
        desc = {'node_id': self.node_id, 'version': '4.0.0'}
        
        info = ServiceInfo(
            "_synthesus._tcp.local.",
            f"{self.node_id}._synthesus._tcp.local.",
            addresses=[socket.inet_aton(local_ip)],
            port=self.port,
            properties=desc,
            server=f"{self.node_id}.local.",
        )
        
        logger.info(f"Advertising Synthesus node {self.node_id} at {local_ip}:{self.port}")
        self.zeroconf.register_service(info)

    def browse(self):
        """Start browsing for other Synthesus nodes."""
        browser = ServiceBrowser(self.zeroconf, "_synthesus._tcp.local.", self)
        return browser

    def remove_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        if name in self.peers:
            logger.info(f"Node {name} left the cluster")
            del self.peers[name]

    def add_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        info = zc.get_service_info(type_, name)
        if info:
            address = socket.inet_ntoa(info.addresses[0])
            node_id = info.properties.get(b'node_id', b'unknown').decode()
            self.peers[name] = {'ip': address, 'port': info.port, 'node_id': node_id}
            logger.info(f"Found peer node: {node_id} at {address}:{info.port}")

    def update_service(self, zc: Zeroconf, type_: str, name: str) -> None:
        pass

    def stop(self):
        self.zeroconf.unregister_all_services()
        self.zeroconf.close()

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    node_name = socket.gethostname()
    discovery = SynthesusDiscovery(node_id=node_name)
    discovery.advertise()
    discovery.browse()
    
    try:
        while True:
            time.sleep(1)
    except KeyboardInterrupt:
        discovery.stop()
