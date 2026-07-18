from __future__ import annotations

import base64
import subprocess
from pathlib import Path

import pytest

from packages.knowledge.connectors import github_connector


def test_private_clone_uses_ephemeral_header_and_credential_free_origin(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clone_root = tmp_path / "clone"
    clone_root.mkdir()
    captured: dict[str, object] = {}
    token = "github-test-token-with-enough-entropy"

    monkeypatch.setattr(github_connector.tempfile, "mkdtemp", lambda **_: str(clone_root))

    def fake_run(command, **kwargs):
        captured["command"] = command
        captured["env"] = kwargs["env"]
        return subprocess.CompletedProcess(command, 0, "", "")

    monkeypatch.setattr(github_connector.subprocess, "run", fake_run)

    assert github_connector._clone("owner/private-repo", token, None) == str(clone_root)
    command = captured["command"]
    environment = captured["env"]
    assert isinstance(command, list)
    assert command[-2] == "https://github.com/owner/private-repo.git"
    assert token not in " ".join(command)
    assert isinstance(environment, dict)
    assert environment["GIT_CONFIG_KEY_0"] == "http.https://github.com/.extraHeader"
    header = environment["GIT_CONFIG_VALUE_0"]
    assert isinstance(header, str) and header.startswith("Authorization: Basic ")
    encoded = header.removeprefix("Authorization: Basic ")
    assert base64.b64decode(encoded).decode("utf-8") == f"x-access-token:{token}"


@pytest.mark.parametrize(
    "repo, token, message",
    [
        ("https://embedded-secret@github.com/owner/repo.git", None, "embedded"),
        ("HTTPS://embedded-secret@github.com/owner/repo.git", None, "embedded"),
        ("http://github.com/owner/repo.git", None, "HTTPS"),
        ("HtTp://github.com/owner/repo.git", None, "HTTPS"),
        ("https://github.com/owner/repo.git?token=secret", None, "query or fragment"),
        ("ssh://user:embedded-secret@example.com/owner/repo.git", None, "embedded"),
        ("ftp://user:embedded-secret@example.com/owner/repo.git", None, "embedded"),
        ("ftp://embedded-secret@example.com/owner/repo.git", None, "embedded"),
        ("ssh://git@example.com/owner/repo.git?token=secret", None, "query or fragment"),
        ("https://example.com/owner/repo.git", "private-token", "only to github.com"),
        ("git@github.com:owner/repo.git", "private-token", "requires an HTTPS"),
    ],
)
def test_clone_rejects_credential_urls_and_token_misdirection(
    repo: str,
    token: str | None,
    message: str,
) -> None:
    with pytest.raises(ValueError, match=message):
        github_connector._clone_url(repo, token)


def test_clone_allows_username_only_ssh_remote() -> None:
    repo = "ssh://git@example.com/owner/repo.git"
    assert github_connector._clone_url(repo, None) == (repo, None)


def test_clone_failure_redacts_token_and_removes_temporary_tree(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    clone_root = tmp_path / "failed-clone"
    clone_root.mkdir()
    token = "github-test-token-that-must-not-leak"
    monkeypatch.setattr(github_connector.tempfile, "mkdtemp", lambda **_: str(clone_root))

    def fail(command, **kwargs):
        raise subprocess.CalledProcessError(
            128,
            command,
            stderr=f"remote accidentally echoed {token}",
        )

    monkeypatch.setattr(github_connector.subprocess, "run", fail)

    with pytest.raises(ValueError, match="git exit 128") as error:
        github_connector._clone("owner/private-repo", token, None)
    assert token not in str(error.value)
    assert not clone_root.exists()
