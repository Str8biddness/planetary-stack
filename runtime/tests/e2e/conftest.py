"""
E2E Test Suite - Shared Fixtures
"""
import pytest
from fastapi.testclient import TestClient
from api.production_server import app


@pytest.fixture(scope="session")
def client():
    """Shared test client for all E2E tests."""
    with TestClient(app) as c:
        yield c
