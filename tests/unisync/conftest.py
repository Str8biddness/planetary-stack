from __future__ import annotations

import hashlib
from dataclasses import replace
from datetime import UTC, datetime, timedelta

import pytest

from services.unisync import AuthorizationError, TransferContext


REQUEST_SHA = "1" * 64
LEASE_SHA = "2" * 64


class StrictValidator:
    def __init__(
        self,
        *,
        account_id: str = "account:local",
        request_sha256: str = REQUEST_SHA,
        lease_sha256: str = LEASE_SHA,
        fencing_token: int = 11,
        allow: bool = True,
    ) -> None:
        self.account_id = account_id
        self.request_sha256 = request_sha256
        self.lease_sha256 = lease_sha256
        self.fencing_token = fencing_token
        self.allow = allow
        self.calls: list[TransferContext] = []

    def validate_transfer(self, context: TransferContext) -> None:
        self.calls.append(context)
        if not self.allow:
            raise AuthorizationError("denied by injected admission")
        if context.account_id != self.account_id:
            raise AuthorizationError("wrong account")
        if context.request_sha256 != self.request_sha256:
            raise AuthorizationError("wrong request digest")
        if context.lease_sha256 != self.lease_sha256:
            raise AuthorizationError("wrong lease digest")
        if context.fencing_token != self.fencing_token:
            raise AuthorizationError("wrong fencing token")


@pytest.fixture
def payload() -> bytes:
    return b"planetary-unisync-object:" + bytes(range(64)) * 8


def make_context(
    payload: bytes,
    *,
    transport: str = "in_process",
    account_id: str = "account:local",
    request_sha256: str = REQUEST_SHA,
    lease_sha256: str = LEASE_SHA,
    fencing_token: int = 11,
    expires_delta: timedelta = timedelta(minutes=5),
) -> TransferContext:
    return TransferContext(
        account_id=account_id,
        request_sha256=request_sha256,
        lease_sha256=lease_sha256,
        fencing_token=fencing_token,
        selected_transport=transport,
        source_node_id="node:source",
        destination_node_id="node:destination",
        object_sha256=hashlib.sha256(payload).hexdigest(),
        byte_length=len(payload),
        expires_at=datetime.now(UTC) + expires_delta,
    )


def replace_context(context: TransferContext, **changes) -> TransferContext:
    return replace(context, **changes)
