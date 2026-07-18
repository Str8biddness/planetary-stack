"""Explicitly deferred Unisync transport interfaces."""

from __future__ import annotations


class DeferredTransport:
    """Placeholder for transports that are not implemented in this wave."""

    def __init__(self, transport_id: str) -> None:
        self.transport_id = transport_id

    def upload_object(self, *args, **kwargs):
        raise NotImplementedError(f"{self.transport_id} is a deferred interface, not a simulated backend")


INTERNET_RELAY = DeferredTransport("internet_mtls_relay")
NAT_TRAVERSAL = DeferredTransport("nat_traversal")
PUBLIC_DISCOVERY = DeferredTransport("public_discovery")
NODE_ENROLLMENT = DeferredTransport("node_enrollment")
