import grpc
import logging
from concurrent import futures
import time

from . import cluster_pb2
from . import cluster_pb2_grpc

logger = logging.getLogger("grpc_server")

class ClusterServicer(cluster_pb2_grpc.ClusterServiceServicer):
    """Implementation of the gRPC Cluster Service for AIOS nodes."""

    def __init__(self, node_id: str):
        self.node_id = node_id
        self.params = {}

    def SyncParameters(self, request, context):
        logger.info(f"Received parameters from {request.node_id}")
        self.params.update(request.parameters)
        return cluster_pb2.SyncResponse(success=True, message="Updated successfully")

    def StreamMemory(self, request, context):
        logger.info(f"Streaming memory shard {request.shard_key}")
        # Logic to read from 5TB drive or local cache
        yield cluster_pb2.MemoryShard(shard_key=request.shard_key, data=b"...", is_last=True)

    def Heartbeat(self, request, context):
        return cluster_pb2.Ack(ok=True)

def serve(node_id: str, port: int = 5051):
    server = grpc.server(futures.ThreadPoolExecutor(max_workers=10))
    cluster_pb2_grpc.add_ClusterServiceServicer_to_server(
        ClusterServicer(node_id), server
    )
    server.add_insecure_port(f'[::]:{port}')
    server.start()
    logger.info(f"gRPC Server started on port {port}")
    return server
