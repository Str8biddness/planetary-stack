"""Tiny developer HTTP mirror for the artifacts directory.

Useful for local end-to-end sync tests:

    python -m synthesus_knowledge_cloud serve --root artifacts --port 8765
    SYNTHESUS_KNOWLEDGE_CLOUD_URL=http://127.0.0.1:8765 python -m \
        synthesus_knowledge_cloud sync --dest /tmp/data
"""

from __future__ import annotations

import http.server
import socketserver
from functools import partial
from pathlib import Path


class _QuietHandler(http.server.SimpleHTTPRequestHandler):
    def log_message(self, format: str, *args) -> None:  # noqa: A002 - stdlib signature
        return


def serve(root: str | Path, *, host: str = "127.0.0.1", port: int = 8765) -> None:
    root_path = Path(root).resolve()
    if not root_path.exists():
        raise FileNotFoundError(root_path)
    handler = partial(_QuietHandler, directory=str(root_path))
    with socketserver.ThreadingTCPServer((host, port), handler) as httpd:
        print(f"serving {root_path} at http://{host}:{port}")
        try:
            httpd.serve_forever()
        except KeyboardInterrupt:
            pass
