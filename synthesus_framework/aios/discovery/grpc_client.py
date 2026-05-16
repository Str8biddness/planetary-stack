import grpc
import logging

from . import cluster_pb2
from . import cluster_pb2_grpc

logger = logging.getLogger("grpc_client")

class ClusterClient:
    """Client to communicate with other AIOS nodes via gRPC."""

    def __init__(self, target_address: str):
        self.channel = grpc.insecure_channel(target_address)
        self.stub = cluster_pb2_grpc.ClusterServiceStub(self.channel)

    def sync_params(self, node_id: str, params: dict):
        try:
            request = cluster_pb2.ParameterRequest(node_id=node_id, parameters=params)
            response = self.stub.SyncParameters(request, timeout=5)
            return response
        except Exception as e:
            logger.error(f"Failed to sync parameters: {e}")
            return None

    def stream_memory(self, shard_key: str):
        try:
            request = cluster_pb2.MemoryRequest(shard_key=shard_key, start_index=0)
            return self.stub.StreamMemory(request)
        except Exception as e:
            logger.error(f"Failed to stream memory: {e}")
            return None

    def close(self):
        self.channel.close()
