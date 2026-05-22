import http.server
import json
import socketserver
import threading
from pathlib import Path

from synthesus_knowledge_cloud.manifest import build_manifest, write_manifest
from synthesus_knowledge_cloud.mirrors import resolve_mirrors
from synthesus_knowledge_cloud.sync import sync_bundle


def _make_bundle(root: Path) -> None:
    (root / "models").mkdir(parents=True, exist_ok=True)
    (root / "data").mkdir(parents=True, exist_ok=True)
    (root / "models" / "swarm_embedder.pkl").write_bytes(b"a" * 4096)
    (root / "data" / "world_lore.json").write_text(json.dumps({"entries": []}), encoding="utf-8")
    (root / "small.txt").write_text("hello world", encoding="utf-8")
    manifest = build_manifest(root, ["."], kind="test")
    write_manifest(manifest, root / "manifest.json")


def test_sync_parallel_and_idempotent(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    _make_bundle(src)
    dest = tmp_path / "dest"

    report = sync_bundle(dest, mirrors=[f"file://{src}"], workers=2)
    assert report.ok, report.failures
    statuses = [r.status for r in report.results]
    assert any(s == "downloaded" for s in statuses)
    assert "wrote-manifest" in statuses

    report2 = sync_bundle(dest, mirrors=[f"file://{src}"], workers=2)
    assert report2.ok, report2.failures
    assert all(r.status in {"skipped", "wrote-manifest"} for r in report2.results)


def test_sync_mirror_failover(tmp_path: Path) -> None:
    primary_empty = tmp_path / "primary"
    secondary = tmp_path / "secondary"
    primary_empty.mkdir()
    secondary.mkdir()
    _make_bundle(secondary)
    # Primary has no manifest at all, so failover must reach the secondary mirror.
    report = sync_bundle(
        tmp_path / "dest",
        mirrors=[f"file://{primary_empty}", f"file://{secondary}"],
        workers=2,
    )
    assert report.ok, report.failures
    assert report.manifest_mirror == f"file://{secondary}"


def test_resolve_mirrors_precedence(monkeypatch) -> None:
    monkeypatch.setenv("SYNTHESUS_KNOWLEDGE_MIRRORS", "https://m1.example,https://m2.example")
    monkeypatch.setenv("SYNTHESUS_KNOWLEDGE_CLOUD_URL", "https://primary.example")
    mirrors = resolve_mirrors(extra=["https://override.example"])
    assert mirrors[0] == "https://override.example"
    assert "https://m1.example" in mirrors
    assert "https://primary.example" in mirrors


def test_sync_over_real_http(tmp_path: Path) -> None:
    src = tmp_path / "src"
    src.mkdir()
    _make_bundle(src)

    class Handler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, format, *args):  # noqa
            return

    handler = type("H", (Handler,), {})

    class TCP(socketserver.ThreadingTCPServer):
        allow_reuse_address = True

    with TCP(("127.0.0.1", 0), lambda *a, **kw: Handler(*a, directory=str(src), **kw)) as httpd:
        port = httpd.server_address[1]
        t = threading.Thread(target=httpd.serve_forever, daemon=True)
        t.start()
        try:
            report = sync_bundle(tmp_path / "dest", mirrors=[f"http://127.0.0.1:{port}"], workers=2)
        finally:
            httpd.shutdown()
        assert report.ok, report.failures
