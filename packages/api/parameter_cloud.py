# api/parameter_cloud.py
# Parameter Cloud service: persisted parameter store + fetch/update/metrics endpoints

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any, Dict, Optional

try:
    from fastapi import APIRouter, Header, HTTPException
    from pydantic import BaseModel, Field
except ImportError:
    # Mock for testing
    APIRouter = lambda *args, **kwargs: type("MockRouter", (), {"get": lambda *a, **k: lambda f: f, "post": lambda *a, **k: lambda f: f})()
    Header = lambda *args, **kwargs: None
    HTTPException = Exception
    class BaseModel:
        def __init__(self, **kwargs):
            for k, v in kwargs.items():
                setattr(self, k, v)
    def Field(*args, **kwargs): return None


PROJ_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_STORE_PATH = PROJ_ROOT / "data" / "parameter_cloud.json"


def _get_expected_api_key() -> str:
    return os.environ.get("SYNTHESUS_PARAMETER_CLOUD_API_KEY", "")


def _require_auth(authorization: Optional[str]) -> None:
    expected = _get_expected_api_key()
    if not expected:
        return

    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization header")

    parts = authorization.split(" ", 1)
    token = parts[1].strip() if len(parts) == 2 and parts[0].lower() == "bearer" else authorization.strip()

    if token != expected:
        raise HTTPException(status_code=403, detail="Invalid API key")


class ParameterCloudUpdateRequest(BaseModel):
    updates: Dict[str, Any] = Field(default_factory=dict)
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))
    performance_metrics: Optional[Dict[str, Any]] = None


class ParameterCloudFetchResponse(BaseModel):
    parameters: Dict[str, Any]
    version: int
    updated_at_ms: int


class ParameterCloudMetricsRequest(BaseModel):
    metrics: Dict[str, Any] = Field(default_factory=dict)
    timestamp: int = Field(default_factory=lambda: int(time.time() * 1000))


class ParameterCloudStore:
    def __init__(self, store_path: Path = DEFAULT_STORE_PATH):
        self.store_path = store_path
        self._state: Dict[str, Any] = {}
        self._version: int = 0
        self._updated_at_ms: int = int(time.time() * 1000)
        self._metrics: Dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        if not self.store_path.exists():
            self._persist()
            return

        try:
            raw = json.loads(self.store_path.read_text(encoding="utf-8"))
            self._state = raw.get("parameters", {}) if isinstance(raw, dict) else {}
            self._version = int(raw.get("version", 0)) if isinstance(raw, dict) else 0
            self._updated_at_ms = int(raw.get("updated_at_ms", int(time.time() * 1000))) if isinstance(raw, dict) else int(time.time() * 1000)
            self._metrics = raw.get("metrics", {}) if isinstance(raw, dict) else {}
        except Exception:
            # If corrupted, reset to empty but keep file writable
            self._state = {}
            self._version = 0
            self._updated_at_ms = int(time.time() * 1000)
            self._metrics = {}
            self._persist()

    def _persist(self) -> None:
        payload = {
            "parameters": self._state,
            "version": self._version,
            "updated_at_ms": self._updated_at_ms,
            "metrics": self._metrics,
        }
        self.store_path.write_text(json.dumps(payload, indent=2, sort_keys=True), encoding="utf-8")

    def fetch(self) -> ParameterCloudFetchResponse:
        return ParameterCloudFetchResponse(parameters=self._state, version=self._version, updated_at_ms=self._updated_at_ms)

    def update(self, updates: Dict[str, Any]) -> None:
        if not isinstance(updates, dict):
            raise ValueError("updates must be a dict")

        for k, v in updates.items():
            self._state[k] = v

        self._version += 1
        self._updated_at_ms = int(time.time() * 1000)
        self._persist()

    def update_metrics(self, metrics: Dict[str, Any]) -> None:
        if not isinstance(metrics, dict):
            return
        for k, v in metrics.items():
            self._metrics[k] = v
        self._persist()


_store = ParameterCloudStore()
router = APIRouter(prefix="/parameter-cloud", tags=["parameter-cloud"])


@router.get("/fetch", response_model=ParameterCloudFetchResponse)
def fetch_parameters(authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization)
    return _store.fetch()


@router.post("/update")
def update_parameters(payload: ParameterCloudUpdateRequest, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization)
    try:
        _store.update(payload.updates)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))

    if payload.performance_metrics:
        _store.update_metrics(payload.performance_metrics)

    return {"ok": True, "version": _store.fetch().version}


@router.post("/metrics")
def push_metrics(payload: ParameterCloudMetricsRequest, authorization: Optional[str] = Header(default=None)):
    _require_auth(authorization)
    _store.update_metrics(payload.metrics)
    return {"ok": True}
