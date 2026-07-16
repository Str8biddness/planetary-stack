"""
E2E Test Suite - Shared Fixtures
"""
import asyncio

import pytest

from api.production_server import app, shutdown, startup
from tests.asgi_client import MainThreadASGIClient


@pytest.fixture(scope="session")
def client():
    """Shared test client for all E2E tests."""
    asyncio.run(startup())
    try:
        yield MainThreadASGIClient(app)
    finally:
        asyncio.run(shutdown())
