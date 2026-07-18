from __future__ import annotations

import os
from pathlib import Path
import stat
import subprocess

import jwt
import pytest

import accounts


_TEST_JWT_SECRET = "test-only-" + ("j" * 40)
_TEST_API_KEY = "syn_existing_test_key_1234567890"
_TEST_HUMAN_SECRET = "human-session-" + ("h" * 32)


def _env_values(path: Path):
    return dict(
        line.split("=", 1)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line and not line.startswith("#") and "=" in line
    )


def _run_redeploy(tmp_path: Path, initial_env: str | None = None):
    source = tmp_path / "source"
    destination = tmp_path / "install"
    (source / "runtime").mkdir(parents=True)
    (source / "desktop").mkdir()
    destination.mkdir()
    env_path = destination / "synthesus.env"
    if initial_env is not None:
        env_path.write_text(initial_env, encoding="utf-8")
        os.chmod(env_path, 0o644)

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("pkill", "sleep"):
        tool = fake_bin / command
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(0o700)

    script = Path(__file__).parents[1] / "tools" / "redeploy_install.sh"
    completed = subprocess.run(
        [str(script), str(source), str(destination)],
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        timeout=30,
    )
    return completed, env_path


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
    os.chmod(parent, 0o700)
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


def test_redeploy_generates_all_owner_only_secrets(tmp_path):
    completed, env_path = _run_redeploy(tmp_path)
    assert completed.returncode == 0, completed.stderr

    values = _env_values(env_path)
    assert len(values["SYNTHESUS_API_KEY"]) >= 24
    assert len(values["SYNTHESUS_JWT_SECRET"]) >= 32
    assert len(values["SYNTHESUS_HUMAN_SESSION_SECRET"]) >= 32
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_redeploy_migrates_missing_or_insecure_secrets(tmp_path):
    initial = "\n".join(
        (
            "SYNTHESUS_API_KEY=dev-key-change-me",
            "SYNTHESUS_JWT_SECRET=dev_secret_change_me",
            f"SYNTHESUS_HUMAN_SESSION_SECRET={_TEST_HUMAN_SECRET}",
            "SYNTHESUS_MODEL=test-model",
            "",
        )
    )
    completed, env_path = _run_redeploy(tmp_path, initial)
    assert completed.returncode == 0, completed.stderr

    values = _env_values(env_path)
    assert values["SYNTHESUS_API_KEY"] != "dev-key-change-me"
    assert values["SYNTHESUS_JWT_SECRET"] != "dev_secret_change_me"
    assert len(values["SYNTHESUS_API_KEY"]) >= 24
    assert len(values["SYNTHESUS_JWT_SECRET"]) >= 32
    assert values["SYNTHESUS_HUMAN_SESSION_SECRET"] == _TEST_HUMAN_SECRET
    assert values["SYNTHESUS_MODEL"] == "test-model"
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


def test_redeploy_rotates_long_whitespace_secrets_that_runtime_rejects(tmp_path):
    initial = "\n".join(
        (
            f"SYNTHESUS_API_KEY={' ' * 32}",
            f"SYNTHESUS_JWT_SECRET={' ' * 48}",
            f"SYNTHESUS_HUMAN_SESSION_SECRET={_TEST_HUMAN_SECRET}",
            "",
        )
    )
    completed, env_path = _run_redeploy(tmp_path, initial)
    assert completed.returncode == 0, completed.stderr

    values = _env_values(env_path)
    assert len(values["SYNTHESUS_API_KEY"]) >= 24
    assert not any(character.isspace() for character in values["SYNTHESUS_API_KEY"])
    assert len(values["SYNTHESUS_JWT_SECRET"]) >= 32
    assert not any(character.isspace() for character in values["SYNTHESUS_JWT_SECRET"])
    assert values["SYNTHESUS_HUMAN_SESSION_SECRET"] == _TEST_HUMAN_SECRET


def test_redeploy_preserves_valid_install_identity(tmp_path):
    jwt_secret = "existing-jwt-" + ("s" * 40)
    initial = "\n".join(
        (
            f"SYNTHESUS_API_KEY={_TEST_API_KEY}",
            f"SYNTHESUS_JWT_SECRET={jwt_secret}",
            f"SYNTHESUS_HUMAN_SESSION_SECRET={_TEST_HUMAN_SECRET}",
            "SYNTHESUS_KNOWLEDGE_SYNC_MODE=off",
            "",
        )
    )
    completed, env_path = _run_redeploy(tmp_path, initial)
    assert completed.returncode == 0, completed.stderr

    values = _env_values(env_path)
    assert values["SYNTHESUS_API_KEY"] == _TEST_API_KEY
    assert values["SYNTHESUS_JWT_SECRET"] == jwt_secret
    assert values["SYNTHESUS_HUMAN_SESSION_SECRET"] == _TEST_HUMAN_SECRET
    assert stat.S_IMODE(env_path.stat().st_mode) == 0o600


@pytest.mark.parametrize("unsafe_kind", ["symlink", "directory"])
def test_redeploy_refuses_unsafe_secret_path(tmp_path, unsafe_kind):
    source = tmp_path / "source"
    destination = tmp_path / "install"
    (source / "runtime").mkdir(parents=True)
    (source / "desktop").mkdir()
    destination.mkdir()
    env_path = destination / "synthesus.env"
    target = tmp_path / "must-not-change"
    target.write_text("sentinel", encoding="utf-8")
    if unsafe_kind == "symlink":
        env_path.symlink_to(target)
    else:
        env_path.mkdir()

    fake_bin = tmp_path / "bin"
    fake_bin.mkdir()
    for command in ("pkill", "sleep"):
        tool = fake_bin / command
        tool.write_text("#!/bin/sh\nexit 0\n", encoding="utf-8")
        tool.chmod(0o700)
    script = Path(__file__).parents[1] / "tools" / "redeploy_install.sh"
    completed = subprocess.run(
        [str(script), str(source), str(destination)],
        env={**os.environ, "PATH": f"{fake_bin}:/usr/bin:/bin"},
        text=True,
        capture_output=True,
        timeout=30,
    )

    assert completed.returncode != 0
    assert "secret" in completed.stderr.lower()
    assert target.read_text(encoding="utf-8") == "sentinel"


def test_full_installer_writes_secrets_atomically_and_owner_only():
    source = (Path(__file__).parents[1] / "install.sh").read_text(encoding="utf-8")
    assert 'if [ -e "$SYNTHESUS_HOME/synthesus.env" ] && [ ! -f' in source
    assert 'install -d -m 0700 "$SYNTHESUS_HOME"' in source
    assert 'mktemp "$SYNTHESUS_HOME/.synthesus.env.tmp.XXXXXX"' in source
    assert 'mv -f "$ENV_TMP" "$SYNTHESUS_HOME/synthesus.env"' in source
    assert 'secret_needs_rotation "$KEY" "dev-key-change-me" 24' in source
    assert 'secret_needs_rotation "$JWT_SECRET_VALUE" "dev_secret_change_me" 32' in source
    assert '.synthesus.env.tmp.$$' not in source


def test_release_ui_has_no_legacy_grid_kvm_or_simulated_update_path():
    desktop = Path(__file__).parent
    script = (desktop / "script.js").read_text(encoding="utf-8")
    markup = (desktop / "index.html").read_text(encoding="utf-8")

    for forbidden in (
        "127.0.0.1:8082",
        "/api/grid/",
        "ws/grid-state",
        "gridSocket",
        "initGridStateSync",
        "node_index",
        "requestPointerLock",
        "virtual_mousedown",
        "checkOTAUpdates",
        "runOTASequence",
        "Verifying cryptographic signatures",
    ):
        assert forbidden not in script

    combined = f"{markup}\n{script}".lower()
    for forbidden in (
        "installer-modal",
        "ota-modal",
        "ring-0",
        "nothing leaves this machine",
        "never leave your machine",
        "no personal data is ever transmitted",
        "runs 100% offline",
        "no cloud, no telemetry",
        "operates unconditionally",
        "kernel online",
        "drive mounted",
        "grid online",
    ):
        assert forbidden not in combined

    disclosure = (
        "Secure mesh enrollment, resource sharing, browser KVM, and Web Desktop "
        "updates are not enabled in this release. Network behavior depends on the "
        "feature used"
    )
    assert disclosure in markup
    assert "Authenticated Terminal" in markup
    assert script.count("new WebSocket(") == 1
    assert "['synthesus-terminal', config.terminal_token]" in script
    assert "URLSearchParams" not in script
    assert "node_id=" not in script
    assert "user_id=" not in script
    assert "mode=worker" not in script
    assert "check provider state in Vitals" not in markup
    assert "ready · local SI larynx" not in markup
    assert "availability is verified when SPEAK runs" in markup
    assert "not checked · press SPEAK to verify backend" in markup


def test_native_status_does_not_claim_unimplemented_ssi_or_kvm():
    source = Path(__file__).with_name("synthesus_native_shell.py").read_text(
        encoding="utf-8"
    )
    assert '"3way_drive_active": False' in source
    assert '"peripheral_bridge_active": False' in source
