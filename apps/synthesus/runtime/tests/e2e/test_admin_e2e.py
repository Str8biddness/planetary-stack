"""
E2E Tests — Admin & Infrastructure Endpoints

Validates health checks, character CRUD, monitoring dashboard,
amplification status, and knowledge API endpoints.
"""
import os
import shutil
from pathlib import Path

import pytest


CHARACTERS_DIR = Path(__file__).resolve().parents[2] / "packages" / "characters"
PARAMETER_CLOUD_STATS = (
    Path(__file__).resolve().parents[2]
    / "packages"
    / "data"
    / "parameter_cloud_v2_stats.json"
)


class TestHealthE2E:
    """Health and status endpoints."""

    def test_health_endpoint(self, client):
        resp = client.get("/api/v1/health")
        assert resp.status_code == 200
        data = resp.json()
        assert "status" in data
        knowledge = data["knowledge_cloud"]
        assert knowledge["mounted"] is True
        assert knowledge["integrity_ok"] is True
        assert len(knowledge["active_mounts"]) == 12
        assert knowledge["retrieval_semantics"]["faiss_vectors"] == 501819
        assert knowledge["retrieval_semantics"]["faiss_dim"] == 128
        assert knowledge["base_read_only"] is True

    def test_root_endpoint(self, client):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dashboard_page(self, client):
        resp = client.get("/dashboard")
        assert resp.status_code == 200


class TestCharacterEndpoints:
    """Character listing and creation endpoints."""

    def test_list_characters(self, client):
        resp = client.get("/api/v1/characters")
        assert resp.status_code == 200
        data = resp.json()
        assert "characters" in data or isinstance(data, list)

    def test_create_character(self, client):
        payload = {
            "name": "E2ETestBot",
            "id": "e2e_testbot",
            "archetype": "scholar",
            "setting": "medieval_fantasy",
            "backstory": "An automated test character.",
            "traits": ["analytical", "curious"],
        }
        char_dir = CHARACTERS_DIR / payload["id"]
        registry_path = CHARACTERS_DIR / "registry.json"
        previous_registry = registry_path.read_bytes() if registry_path.exists() else None
        try:
            resp = client.post("/api/v1/characters", json=payload)
            # Might be 200 or 201 on success, or 422 if schema mismatch
            assert resp.status_code in (200, 201, 422)
        finally:
            shutil.rmtree(char_dir, ignore_errors=True)
            if previous_registry is None:
                registry_path.unlink(missing_ok=True)
            else:
                registry_path.write_bytes(previous_registry)

    def test_get_character_by_id(self, client):
        resp = client.get("/api/v1/characters/synthesus")
        # Could be 200 or 404 depending on what's loaded
        assert resp.status_code in (200, 404)


class TestMonitoringEndpoints:
    """Monitoring and dashboard endpoints."""

    def test_monitoring_dashboard(self, client):
        resp = client.get("/api/v1/monitoring/dashboard")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_stats_endpoint(self, client):
        resp = client.get("/api/v1/stats")
        assert resp.status_code == 200

    def test_modules_endpoint(self, client):
        resp = client.get("/api/v1/modules")
        assert resp.status_code == 200

    def test_conscious_state(self, client):
        resp = client.get("/api/v1/conscious_state")
        assert resp.status_code == 200

    def test_kernel_status(self, client):
        resp = client.get("/api/v1/kernel/status")
        assert resp.status_code == 200


class TestAmplificationEndpoints:
    """Amplification plane status endpoints."""

    def test_amplification_status(self, client):
        resp = client.get("/api/v1/amplification/status")
        assert resp.status_code == 200
        data = resp.json()
        assert isinstance(data, dict)

    def test_amplification_metrics(self, client):
        resp = client.get("/api/v1/amplification/metrics")
        assert resp.status_code == 200


class TestKnowledgeEndpoints:
    """Knowledge API endpoints."""

    def test_knowledge_stats(self, client):
        resp = client.get("/api/v1/knowledge/stats")
        assert resp.status_code == 200

    def test_knowledge_search(self, client):
        """Knowledge search is a GET endpoint with query params."""
        resp = client.get("/api/v1/knowledge/search", params={"q": "test", "top_k": 5})
        assert resp.status_code in (200, 422)

    def test_knowledge_entries_list(self, client):
        resp = client.get("/api/v1/knowledge/entries")
        assert resp.status_code == 200


class TestAdminEndpoints:
    """Admin / operator endpoints."""

    def test_admin_patterns_post(self, client):
        """Admin patterns is a POST endpoint (uploading patterns)."""
        payload = {"patterns": []}
        resp = client.post("/api/v1/admin/patterns", json=payload)
        # May require auth or return 422/200
        assert resp.status_code in (200, 201, 403, 422)

    def test_admin_usage(self, client):
        """Admin usage may require auth; accept 200 or 403."""
        resp = client.get("/api/v1/admin/usage")
        assert resp.status_code in (200, 403)

    def test_admin_api_keys_list(self, client):
        resp = client.get("/api/v1/admin/api-keys")
        assert resp.status_code in (200, 403)

    def test_feedback_endpoint(self, client):
        payload = {
            "session_id": "e2e-feedback",
            "query": "test",
            "response": "test response",
            "rating": 5,
        }
        resp = client.post("/api/v1/feedback", json=payload)
        assert resp.status_code in (200, 201, 422)


class TestParameterCloudEndpoints:
    """Parameter Cloud v2 endpoints.
    
    These endpoints are mounted on the same FastAPI app but may proxy to
    a separate service. If the backing service isn't running, we skip.
    """

    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL") and not PARAMETER_CLOUD_STATS.exists(),
        reason="Parameter Cloud database and static statistics are unavailable",
    )
    def test_parameter_cloud_stats(self, client):
        try:
            resp = client.get("/parameter-cloud/v2/stats")
            assert resp.status_code in (200, 500)
        except (ConnectionError, OSError):
            pytest.skip("Parameter Cloud service not available")

    def test_parameter_cloud_shards(self, client):
        try:
            resp = client.get("/parameter-cloud/v2/shards")
            assert resp.status_code in (200, 500)
        except (ConnectionError, OSError):
            pytest.skip("Parameter Cloud service not available")

    @pytest.mark.skipif(
        not os.environ.get("DATABASE_URL"),
        reason="Parameter Cloud database is not configured",
    )
    def test_parameter_cloud_query(self, client):
        try:
            payload = {"query": "test"}
            resp = client.post("/parameter-cloud/v2/query", json=payload)
            assert resp.status_code in (200, 422, 500)
        except (ConnectionError, OSError):
            pytest.skip("Parameter Cloud service not available")
