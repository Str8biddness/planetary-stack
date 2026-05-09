"""
Synthesus 4.0 — Cybersecurity Agent REST API Router

Provides 13 endpoints for security operations, alert management,
threat intelligence, and system integrity monitoring.

Mount this router in production_server.py:
    app.include_router(security_router, prefix="/api/v1/security", tags=["security"])
"""

import logging
from typing import Optional

from fastapi import APIRouter, HTTPException, BackgroundTasks  # type: ignore
from api.security_schemas import (  # type: ignore
    ScanRequest,
    ScanResponse,
    BreachExerciseRequest,
    BreachExerciseResponse,
    BruteSimRequest,
    BruteSimResponse,
    AlertListResponse,
    AlertResponse,
    AlertStatsResponse,
    SecurityStatusResponse,
    ThreatFeedResponse,
    ThreatFeedEntry,
)

logger = logging.getLogger(__name__)

security_router = APIRouter()

# The SecurityAgent instance is set by production_server.py at startup
_security_agent = None


def set_security_agent(agent):
    """Called by production_server.py to inject the SecurityAgent instance."""
    global _security_agent
    _security_agent = agent


def _get_agent():
    if _security_agent is None:
        raise HTTPException(status_code=503, detail="Security agent not initialized")
    return _security_agent


# ─── Scan Endpoints ──────────────────────────────────────────────────

@security_router.post("/scan", response_model=ScanResponse)
async def trigger_scan(request: ScanRequest = ScanRequest()):
    """Trigger a full system security scan."""
    agent = _get_agent()
    result = await agent.run_full_scan()
    return ScanResponse(**result)


@security_router.post("/scan/breach", response_model=BreachExerciseResponse)
async def trigger_breach(request: BreachExerciseRequest = BreachExerciseRequest()):
    """Run a Breach red-team exercise."""
    agent = _get_agent()
    target_config = {
        "type": "api_triggered",
        "services": request.services,
        "debug_mode": request.debug_mode,
        "exposed_files": request.exposed_files,
    }
    result = await agent.run_breach_exercise(target_config)
    return BreachExerciseResponse(**result)


@security_router.post("/scan/brute", response_model=BruteSimResponse)
async def trigger_brute(request: BruteSimRequest = BruteSimRequest()):
    """Run a brute-force credential pressure simulation."""
    agent = _get_agent()
    result = await agent.run_brute_simulation(
        pattern=request.pattern,
        duration=request.duration_seconds,
        rps=request.requests_per_second,
    )
    return BruteSimResponse(**result)


# ─── Alert Endpoints ─────────────────────────────────────────────────

@security_router.get("/alerts", response_model=AlertListResponse)
async def list_alerts(
    severity: Optional[str] = None,
    status: Optional[str] = None,
    source: Optional[str] = None,
    limit: int = 50,
    offset: int = 0,
):
    """List security alerts with optional filters."""
    agent = _get_agent()
    alerts = agent.alert_store.get_alerts(
        severity=severity,
        status=status,
        source=source,
        limit=limit,
        offset=offset,
    )
    stats = agent.alert_store.get_stats()
    return AlertListResponse(
        alerts=[AlertResponse(**a) for a in alerts],
        total=stats["total"],
        filters={"severity": severity, "status": status, "source": source},
    )


@security_router.get("/alerts/stats", response_model=AlertStatsResponse)
async def alert_stats():
    """Get alert statistics summary."""
    agent = _get_agent()
    stats = agent.alert_store.get_stats()
    return AlertStatsResponse(**stats)


@security_router.get("/alerts/{alert_id}", response_model=AlertResponse)
async def get_alert(alert_id: int):
    """Get a single alert by ID."""
    agent = _get_agent()
    alert = agent.alert_store.get_alert(alert_id)
    if not alert:
        raise HTTPException(status_code=404, detail="Alert not found")
    return AlertResponse(**alert)


@security_router.post("/alerts/{alert_id}/acknowledge")
async def acknowledge_alert(alert_id: int):
    """Acknowledge a security alert."""
    agent = _get_agent()
    success = agent.alert_store.acknowledge_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "acknowledged", "alert_id": alert_id}


@security_router.post("/alerts/{alert_id}/resolve")
async def resolve_alert(alert_id: int):
    """Resolve a security alert."""
    agent = _get_agent()
    success = agent.alert_store.resolve_alert(alert_id)
    if not success:
        raise HTTPException(status_code=404, detail="Alert not found")
    return {"status": "resolved", "alert_id": alert_id}


# ─── Intelligence Endpoints ──────────────────────────────────────────

@security_router.get("/baseline")
async def view_baseline():
    """View the current normalcy baseline."""
    agent = _get_agent()
    return {
        "sample_count": agent.baseliner.sample_count,
        "baseline": agent.baseliner.baseline,
    }


@security_router.get("/integrity")
async def check_integrity():
    """Run an immune system integrity check."""
    agent = _get_agent()
    anomalies = agent.immune_system.check_integrity()
    return {
        "status": "compromised" if anomalies else "clean",
        "anomalies": anomalies,
        "files_monitored": len(agent.immune_system.critical_files),
    }


@security_router.get("/ghostnet/threats", response_model=ThreatFeedResponse)
async def ghostnet_threats():
    """Get the GhostNet P2P threat feed."""
    agent = _get_agent()
    threats = agent.ghost_net.get_recent_external_threats()
    entries = [
        ThreatFeedEntry(source="ghostnet", threat=t, severity="medium")
        for t in threats
    ]
    return ThreatFeedResponse(threats=entries, total=len(entries))


# ─── Status Endpoints ────────────────────────────────────────────────

@security_router.get("/status")
async def security_status():
    """Get the overall security agent status."""
    agent = _get_agent()
    state = agent.get_dashboard_state()
    return state


@security_router.post("/chat")
async def security_chat(request: Dict[str, Any]):
    """Conversational interface to the security agent."""
    agent = _get_agent()
    message = request.get("message", "").lower()
    
    # Logic for handling specific security questions
    if "status" in message or "how are we" in message:
        state = agent.get_dashboard_state()
        return {"response": f"System status is currently {state['overall_status'].upper()}. I am monitoring {len(state['recent_alerts'])} active alerts and {len(state['ghostnet_peers'])} collaborative peers."}
    
    if "threat" in message or "breach" in message:
        recent = agent.alert_store.get_alerts(severity="high", limit=1)
        if recent:
            narrative = agent.explainer.narrate_incident(recent[0])
            return {"response": f"I have detected potential activity. {narrative}"}
        return {"response": "No high-confidence threats are currently active in the local environment."}

    if "who are you" in message or "persona" in message:
        return {"response": "I am Aegis, the Synthesus 4.0 Cognitive Security Officer. I utilize causal and Bayesian reasoning to protect your infrastructure with autonomous resilience."}

    # Default generative response using Aegis Explainer logic
    return {"response": "I am standing by for security commands. You can ask me about system status, current threats, or run a breach exercise."}


@security_router.get("/report")
async def security_report():
    """Generate a JSON security summary report."""
    agent = _get_agent()
    state = agent.get_dashboard_state()
    system_info = await agent.security_tools.get_system_info()

    return {
        "report_type": "security_summary",
        "generated_at": __import__("datetime").datetime.utcnow().isoformat(),
        "overall_status": state["overall_status"],
        "system_info": system_info,
        "alert_stats": state["alert_stats"],
        "recent_alerts": state["recent_alerts"][:10],
        "recent_scans": state["recent_scans"],
        "ghostnet_threats": state["ghostnet_threats"],
        "subsystems": state["subsystems"],
    }
