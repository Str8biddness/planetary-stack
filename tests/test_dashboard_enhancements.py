import pytest
import logging
from fastapi.testclient import TestClient
from api.production_server import app, logger

client = TestClient(app)

def test_monitoring_dashboard_enhancements():
    # Trigger a warning log to see if it gets captured by MemoryLogHandler
    logger.warning("This is a test warning for the dashboard stream.")
    
    response = client.get("/api/v1/monitoring/dashboard")
    assert response.status_code == 200, response.text
    
    data = response.json()
    assert "system" in data
    assert "recent_logs" in data
    
    logs = data["recent_logs"]
    assert isinstance(logs, list)
    
    # We should have at least the warning we just emitted
    test_log = next((log for log in logs if "test warning" in log["message"]), None)
    assert test_log is not None
    assert test_log["level"] == "WARNING"
    assert test_log["component"] == "synthesus.api"
    
    assert "cognitive_state" in data
    assert "belief_count" in data["cognitive_state"]
