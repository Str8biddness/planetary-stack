import pytest
import os
import shutil

from api.production_server import CHARACTERS_DIR, app
from tests.asgi_client import MainThreadASGIClient

client = MainThreadASGIClient(
    app,
    headers={"X-API-Key": os.environ["SYNTHESUS_API_KEY"]},
)

def test_create_character():
    char_dir = CHARACTERS_DIR / "testbot"
    registry_path = CHARACTERS_DIR / "registry.json"
    registry_before = registry_path.read_bytes() if registry_path.exists() else None
    payload = {
        "name": "TestBot",
        "id": "testbot",
        "archetype": "scholar",
        "setting": "sci_fi",
        "traits": ["analytical", "curious"],
        "backstory": "A test bot from the future.",
        "location": "Server Room",
        "establishment": "Testing Lab",
        "specialty": "quality assurance",
        "rank": "Lead Tester",
        "years": 5,
        "inventory_desc": "logs and metrics"
    }

    try:
        response = client.post("/api/v1/characters", json=payload)

        # Check if the endpoint responds correctly
        assert response.status_code == 200, response.text
        data = response.json()
        assert data["character_id"] == "testbot"
        assert data["name"] == "TestBot"
        assert data["archetype"] == "scholar"

        # CharacterFactory writes into the production server's configured root.
        assert char_dir.exists()
        assert (char_dir / "bio.json").exists()
        assert (char_dir / "patterns.json").exists()
    finally:
        shutil.rmtree(char_dir, ignore_errors=True)
        if registry_before is None:
            registry_path.unlink(missing_ok=True)
        else:
            registry_path.write_bytes(registry_before)
