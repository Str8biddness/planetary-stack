from __future__ import annotations

import os
from pathlib import Path
import stat

import jwt
import pytest

import accounts


_TEST_JWT_SECRET = "test-only-" + ("j" * 40)


@pytest.fixture
def isolated_accounts(monkeypatch, tmp_path):
    database = tmp_path / "private" / "accounts.db"
    monkeypatch.setattr(accounts, "DB_PATH", str(database))
    monkeypatch.delenv("JWT_SECRET", raising=False)
    monkeypatch.setenv("SYNTHESUS_JWT_SECRET", _TEST_JWT_SECRET)
    return database


@pytest.mark.parametrize(
    "secret",
    [None, "", "dev_secret_change_me", "too-short"],
)
def test_account_jwt_secret_fails_closed(monkeypatch, secret):
    monkeypatch.delenv("JWT_SECRET", raising=False)
    if secret is None:
        monkeypatch.delenv("SYNTHESUS_JWT_SECRET", raising=False)
    else:
        monkeypatch.setenv("SYNTHESUS_JWT_SECRET", secret)

    with pytest.raises(RuntimeError, match="unique per-install JWT secret"):
        accounts.require_secure_configuration()


def test_account_tokens_use_only_the_install_secret(isolated_accounts):
    accounts.init_db()
    result = accounts.register("owner@example.test", "correct-horse-battery")

    assert accounts.verify_token(result["token"])["email"] == "owner@example.test"
    forged = jwt.encode(
        {"sub": "1", "email": "owner@example.test"},
        "dev_secret_change_me",
        algorithm=accounts.JWT_ALGO,
    )
    assert accounts.verify_token(forged) is None


def test_account_database_is_owner_confined(isolated_accounts):
    accounts.init_db()

    assert stat.S_IMODE(isolated_accounts.parent.stat().st_mode) == 0o700
    assert stat.S_IMODE(isolated_accounts.stat().st_mode) == 0o600
    assert isolated_accounts.stat().st_uid == os.geteuid()


def test_account_database_refuses_permissive_custom_parent(monkeypatch, tmp_path):
    parent = tmp_path / "shared"
    parent.mkdir(mode=0o755)
    os.chmod(parent, 0o755)
    monkeypatch.setattr(accounts, "DB_PATH", str(parent / "accounts.db"))

    with pytest.raises(RuntimeError, match="must be owner-only"):
        accounts.init_db()
    assert stat.S_IMODE(parent.stat().st_mode) == 0o755


def test_account_database_symlink_is_rejected(monkeypatch, tmp_path):
    if not hasattr(os, "O_NOFOLLOW"):
        pytest.skip("platform has no O_NOFOLLOW")

    parent = tmp_path / "private"
    parent.mkdir()
    target = tmp_path / "target.db"
    target.write_bytes(b"do-not-touch")
    database = parent / "accounts.db"
    database.symlink_to(target)
    monkeypatch.setattr(accounts, "DB_PATH", str(database))

    with pytest.raises(RuntimeError, match="database path is unsafe"):
        accounts.init_db()
    assert target.read_bytes() == b"do-not-touch"


def test_legacy_terminal_route_is_a_nonexecuting_tombstone():
    source = Path(__file__).with_name("synthesus_native_shell.py").read_text(
        encoding="utf-8"
    )
    route_start = source.index("@app.route('/api/terminal/run'")
    route_end = source.index("# LAUNCHER", route_start)
    route_source = source[route_start:route_end]

    assert "legacy_terminal_transport_removed" in route_source
    assert "410" in route_source
    assert "subprocess" not in route_source
    assert "admin_override" not in route_source
    assert "shell=True" not in source


def test_native_shell_has_no_runtime_api_key_fallback():
    source = Path(__file__).with_name("synthesus_native_shell.py").read_text(
        encoding="utf-8"
    )
    assert 'os.environ.get("SYNTHESUS_API_KEY", "dev-key-change-me")' not in source
    assert '"3way_drive_active": False' in source
