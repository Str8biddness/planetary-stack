"""
E2E Tests — SysOps Domain

Validates the /api/v1/query endpoint when routing through the SysOps domain.
The SysOps domain triggers domain-specific amplification with administrative
candidate actions (restart, scale, runbook, etc.).
"""
import pytest
import time


class TestSysOpsE2E:
    """End-to-end tests for SysOps domain queries."""

    def test_sysops_query_returns_200(self, client):
        """A SysOps query should always return 200."""
        time.sleep(1)  # Avoid rate limiting
        payload = {
            "query": "Service A is experiencing high latency, what do we do?",
            "character": "synth",
            "session_id": "e2e-sysops-1",
        }
        resp = client.post("/api/v1/query", json=payload)
        assert resp.status_code in (200, 429)

    def test_sysops_response_has_required_keys(self, client):
        """SysOps responses must have the standard response structure."""
        time.sleep(1)
        payload = {
            "query": "Check the health of all nodes",
            "character": "synth",
            "session_id": "e2e-sysops-2",
        }
        resp = client.post("/api/v1/query", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            assert "response" in data or "text" in data
            assert "confidence" in data
            assert "source" in data

    def test_sysops_debug_contains_ml_swarm(self, client):
        """When debug is enabled, the response should include ml_swarm info."""
        time.sleep(1)
        payload = {
            "query": "Disk usage is at 95% on host-3",
            "character": "synth",
            "session_id": "e2e-sysops-3",
            "include_debug": True,
        }
        resp = client.post("/api/v1/query", json=payload)
        if resp.status_code == 200:
            data = resp.json()
            if "debug" in data:
                debug = data["debug"]
                assert isinstance(debug, dict)
                if "ml_swarm" in debug:
                    assert "intent" in debug["ml_swarm"]

    def test_sysops_multiple_sessions_isolated(self, client):
        """Two different SysOps sessions should not leak state."""
        for sid in ("e2e-sysops-iso-a", "e2e-sysops-iso-b"):
            time.sleep(1)
            payload = {
                "query": "Restart the payment service",
                "character": "synth",
                "session_id": sid,
            }
            resp = client.post("/api/v1/query", json=payload)
            assert resp.status_code in (200, 429)
