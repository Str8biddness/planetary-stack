import pytest
import asyncio
from unittest.mock import patch, MagicMock
from fastapi.testclient import TestClient

from api.production_server import app, _character_cache
from amplification_wrapper import AmplificationPlane

# Re-enable amplification plane just in case
import api.production_server
api.production_server._amplification_plane = AmplificationPlane(enabled=True)
api.production_server._amplification_plane._available = True

# Mock the underlying JS call
mock_call_ts = MagicMock(return_value={
    "summaries": [{"whatIsBroken": "Test DB"}],
    "anomalyFlags": [],
    "rankedActions": [
        {"action": {"type": "restart", "target": "host-1"}, "score": 0.9, "riskScore": 0.3}
    ],
    "topTrajectories": [],
    "references": [],
    "sanityCheckPassed": True,
    "executionRecommendation": "PROCEED"
})
api.production_server._amplification_plane._call_ts = mock_call_ts

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_teardown():
    # Inject a SysOps character
    _character_cache["sysops-bot"] = {
        "bio": {
            "name": "SysOps Bot",
            "archetype": "system admin"
        }
    }
    mock_call_ts.reset_mock()
    yield
    if "sysops-bot" in _character_cache:
        del _character_cache["sysops-bot"]

def test_sysops_query_triggers_correct_candidate_actions():
    """
    Test that a query to a sysops character routes to amplify_planning
    with the correct sysops candidate actions.
    """
    payload = {
        "query": "The database is down on host-1",
        "character": "sysops-bot",
        "session_id": "sysops-test-session",
        "mode": "cognitive"
    }
    
    response = client.post("/api/v1/query", json=payload)
    assert response.status_code == 200
    
    # Verify Amplification Plane was called
    assert mock_call_ts.call_count >= 2
    
    # Find the planning call
    planning_call = next((call for call in mock_call_ts.call_args_list if call[0][0] == "planning"), None)
    assert planning_call is not None
    
    # Verify payload
    planning_payload = planning_call[0][1]
    assert planning_payload["worldState"]["domain"] == "sysops"
    
    # Verify candidate actions are sysops specific
    candidate_actions = planning_payload["candidateActions"]
    action_types = [a["type"] for a in candidate_actions]
    assert "restart" in action_types
    assert "runbook" in action_types
    assert "scale" in action_types
    assert "respond" not in action_types  # Should not use generic chat actions
    
    # Verify output call
    output_call = next((call for call in mock_call_ts.call_args_list if call[0][0] == "output"), None)
    if output_call:
        output_payload = output_call[0][1]
        assert output_payload["chosenAction"]["type"] == "restart"
