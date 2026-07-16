import pytest
from fastapi.testclient import TestClient
from api.production_server import app

client = TestClient(app)

def test_create_character():
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

    response = client.post("/api/v1/characters", json=payload)
    
    # Check if the endpoint responds correctly
    assert response.status_code == 200, response.text
    data = response.json()
    assert data["character_id"] == "testbot"
    assert data["name"] == "TestBot"
    assert data["archetype"] == "scholar"
    
    # Check if files were created
    import os
    char_dir = os.path.join("characters", "testbot")
    assert os.path.exists(char_dir)
    assert os.path.exists(os.path.join(char_dir, "bio.json"))
    assert os.path.exists(os.path.join(char_dir, "patterns.json"))
    
    # Clean up test artifact
    import shutil
    shutil.rmtree(char_dir)
