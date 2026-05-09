"""Synthesus 4.0 — Cybersecurity Agent API Schemas"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


# ─── Scan Requests ───────────────────────────────────────────────────

class ScanRequest(BaseModel):
    """Request to trigger a security scan."""
    scan_type: str = Field(default="full", description="Scan type: full, audit, integrity")


class BreachExerciseRequest(BaseModel):
    """Request to run a Breach red-team exercise."""
    services: List[Dict[str, Any]] = Field(default_factory=list, description="Services to scan")
    debug_mode: bool = Field(default=False, description="Whether debug mode is enabled")
    exposed_files: List[str] = Field(default_factory=list, description="Files to check for exposure")


class BruteSimRequest(BaseModel):
    """Request to run a brute-force simulation."""
    pattern: str = Field(default="dictionary", description="Attack pattern: dictionary, spraying, stuffing, timing")
    duration_seconds: int = Field(default=10, ge=1, le=120, description="Simulation duration")
    requests_per_second: float = Field(default=5.0, ge=0.5, le=100.0, description="Request rate")


# ─── Scan Responses ──────────────────────────────────────────────────

class ScanResponse(BaseModel):
    """Response from a security scan."""
    status: str
    findings_count: int = 0
    findings: List[str] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    audit: Optional[Dict[str, Any]] = None
    error: Optional[str] = None


class BreachExerciseResponse(BaseModel):
    """Response from a Breach exercise."""
    status: str
    vectors_found: int = 0
    vectors: List[Dict[str, Any]] = Field(default_factory=list)
    elapsed_ms: float = 0.0
    error: Optional[str] = None


class BruteSimResponse(BaseModel):
    """Response from a brute-force simulation."""
    status: str
    total_attempts: int = 0
    detected_pattern: Optional[str] = None
    timing_anomalies: int = 0
    avg_response_time_ms: float = 0.0
    error: Optional[str] = None


# ─── Alert Models ────────────────────────────────────────────────────

class AlertResponse(BaseModel):
    """Single security alert."""
    id: int
    severity: str
    source: str
    title: str
    description: str
    status: str
    metadata: Dict[str, Any] = Field(default_factory=dict)
    created_at: Optional[str] = None
    acknowledged_at: Optional[str] = None
    resolved_at: Optional[str] = None


class AlertListResponse(BaseModel):
    """Paginated list of alerts."""
    alerts: List[AlertResponse]
    total: int
    filters: Dict[str, Optional[str]] = Field(default_factory=dict)


class AlertStatsResponse(BaseModel):
    """Alert statistics summary."""
    total: int
    active: int
    by_severity: Dict[str, int] = Field(default_factory=dict)
    by_status: Dict[str, int] = Field(default_factory=dict)


# ─── Status Models ───────────────────────────────────────────────────

class SecurityStatusResponse(BaseModel):
    """Overall security agent status."""
    overall_status: str  # secure, monitoring, warning, critical
    alert_stats: AlertStatsResponse
    recent_scans: List[Dict[str, Any]] = Field(default_factory=list)
    ghostnet_threats: List[str] = Field(default_factory=list)
    last_scan_time: Optional[float] = None
    scan_interval_seconds: int = 300
    is_scanning: bool = False
    subsystems: Dict[str, str] = Field(default_factory=dict)


class ThreatFeedEntry(BaseModel):
    """Single entry in the threat feed."""
    source: str
    threat: str
    severity: str
    created_at: Optional[str] = None


class ThreatFeedResponse(BaseModel):
    """Combined threat feed."""
    threats: List[ThreatFeedEntry]
    total: int
