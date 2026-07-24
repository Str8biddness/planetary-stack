import pytest
from pathlib import Path
import httpx
from fastapi.testclient import TestClient

def test_ide_crud_endpoints(tmp_path):
    import os
    os.environ["SYNTHESUS_API_KEY"] = "install-secret"
    os.environ["SYNTHESUS_IDE_ROOT"] = str(tmp_path)
    from apps.synthesus.desktop.synthesusd import create_app, ControllerSettings
    settings = ControllerSettings.from_environment()
    app = create_app(settings)
    client = TestClient(app)
    
    headers = {"X-API-Key": "install-secret"}
    
    # Test Create
    res = client.post("/api/ide/files/create", json={"path": "test.txt", "content": "hello"}, headers=headers)
    assert res.status_code == 200
    assert (tmp_path / "test.txt").read_text() == "hello"
    
    # Test Outside root
    res = client.post("/api/ide/files/create", json={"path": "../outside.txt", "content": "bad"}, headers=headers)
    assert res.status_code == 403
    
    # Test Rename
    res = client.post("/api/ide/files/rename", json={"old_path": "test.txt", "new_path": "test2.txt"}, headers=headers)
    assert res.status_code == 200
    assert not (tmp_path / "test.txt").exists()
    assert (tmp_path / "test2.txt").exists()
    
    res = client.post("/api/ide/files/rename", json={"old_path": "test2.txt", "new_path": "../test3.txt"}, headers=headers)
    assert res.status_code == 403
    
    # Test Delete
    res = client.delete("/api/ide/files/test2.txt", headers=headers)
    assert res.status_code == 200
    assert not (tmp_path / "test2.txt").exists()
    
    res = client.delete("/api/ide/files/../outside.txt", headers=headers)
    assert res.status_code in (403, 404)
