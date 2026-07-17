"""RFC 8785 signing and digest helpers for CHAL/vSource documents."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import rfc8785
from pydantic import BaseModel


def wire_mapping(document: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(document, BaseModel):
        payload = document.model_dump(mode="json", by_alias=True)
    elif isinstance(document, Mapping):
        payload = dict(document)
    else:
        raise TypeError("contract document must be a Pydantic model or mapping")
    return payload


def canonical_document_bytes(
    document: BaseModel | Mapping[str, Any],
    *,
    omit_signature: bool = False,
) -> bytes:
    payload = wire_mapping(document)
    if omit_signature:
        payload.pop("signature", None)
    return rfc8785.dumps(payload)


def signing_bytes(document: BaseModel | Mapping[str, Any]) -> bytes:
    return canonical_document_bytes(document, omit_signature=True)


def document_sha256(document: BaseModel | Mapping[str, Any]) -> str:
    """Return the signed-payload digest, excluding the top-level signature."""

    return hashlib.sha256(signing_bytes(document)).hexdigest()


__all__ = [
    "canonical_document_bytes",
    "document_sha256",
    "signing_bytes",
    "wire_mapping",
]
