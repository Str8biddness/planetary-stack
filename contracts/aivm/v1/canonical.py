"""RFC 8785 signing and digest helpers for AIVM v1 documents."""

from __future__ import annotations

import hashlib
from collections.abc import Mapping
from typing import Any

import rfc8785
from pydantic import BaseModel


def wire_mapping(document: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(document, BaseModel):
        return document.model_dump(mode="json", by_alias=True)
    if isinstance(document, Mapping):
        return dict(document)
    raise TypeError("AIVM contract document must be a Pydantic model or mapping")


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
    return hashlib.sha256(signing_bytes(document)).hexdigest()
