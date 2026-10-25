"""Loopback-only, read-only browser view of the existing local Hub sources."""

from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic
from typing import Any, cast
from urllib.parse import urlsplit

from . import hub
from .registry import ProjectRegistry
from .session_store import SessionMetadataError

ASSETS = Path(__file__).with_name("dashboard")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def collect_snapshot(registry_path: str | None) -> dict[str, Any]:
    """Collect metadata only; saved records are never relabeled as live sessions."""
    registry = ProjectRegistry(registry_path) if registry_path else ProjectRegistry()
    projects: list[dict[str, Any]] = []
    for project_id in registry.project_ids():
        config = registry.get_project_config(project_id)
        projects.append(
            {"id": project_id, "path": config.path, "hub_enabled": config.hub_enabled}
        )
    sessions, sources = hub.discover_claude_sessions(
        [(project["id"], project["path"] or "") for project in projects],
        registry_known=hub._registry_is_known(registry),
    )
    sources.extend(
        {
            "provider": provider,
            "status": "unsupported",
            "session_count": None,
            "observed_at": None,
        }
        for provider in ("Codex", "Gemini CLI")
    )
    return {
        "mode": "live",
        "observed_at": datetime.now(timezone.utc).isoformat(),
        "projects": projects,
        "sessions": sessions,
        "session_sources": sources,
        "saved_sessions": hub.load_sessions(),
    }


def demo_snapshot() -> dict[str, Any]:
    """Explicit sample data for exploring the interface without real sessions."""
    now = datetime.now(timezone.utc).isoformat()
    samples = [
        ("alpha", "Claude Code", "busy", "Review the local changes"),
        ("beta", "Claude Code", "idle", None),
        (None, "Codex", "unknown", None),
    ]
    return {
        "mode": "demo",
        "observed_at": now,
        "projects": [
            {"id": name, "path": f"/work/{name}", "hub_enabled": True}
            for name in ("alpha", "beta", "zeta")
        ],
        "sessions": [
            {
                "session_id": f"demo-{index}",
                "provider": provider,
                "activity": activity,
                "project_id": project,
                "project_path": f"/work/{project}" if project else None,
                "registration": "registered" if project else "unknown",
                "reported_task": task,
                "source": "Demonstration data",
                "observed_at": now,
                "started_at": None,
            }
            for index, (project, provider, activity, task) in enumerate(samples)
        ],
        "session_sources": [
            {
                "provider": "Claude Code",
                "status": "available",
                "session_count": 2,
                "observed_at": now,
            },
            {
                "provider": "Codex",
                "status": "unsupported",
                "session_count": None,
                "observed_at": None,
            },
            {
                "provider": "Gemini CLI",
                "status": "unsupported",
                "session_count": None,
                "observed_at": None,
            },
        ],
        "saved_sessions": [
            {
                "session_id": "saved-zeta",
                "agent": "Codex",
                "project_id": "zeta",
                "reported_task": "Inspect the test report",
                "updated_at": now,
            }
        ],
    }


class _SnapshotCache:
    """Share one short-lived discovery result across local browser tabs."""

    def __init__(self, registry_path: str | None) -> None:
        self.registry_path = registry_path
        self.snapshot: dict[str, Any] | None = None
        self.observed = 0.0
        self.lock = threading.Lock()

    def get(self) -> dict[str, Any]:
        with self.lock:
            if self.snapshot is None or monotonic() - self.observed >= 12:
                self.snapshot = collect_snapshot(self.registry_path)
                self.observed = monotonic()
            return self.snapshot


def create_server(registry_path: str | None, port: int = 8765) -> ThreadingHTTPServer:
    """Bind only to IPv4 loopback and reject foreign browser origins/Host values."""

    cache = _SnapshotCache(registry_path)

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, format: str, *args: Any) -> None:
            """Keep session metadata and local paths out of HTTP access logs."""

        def _send(self, status: int, body: bytes, content_type: str) -> None:
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header(
                "Content-Security-Policy",
                "default-src 'self'; script-src 'self'; style-src 'self'; connect-src 'self'; img-src 'self' data:; frame-ancestors 'none'; base-uri 'none'; form-action 'none'",
            )
            self.end_headers()
            self.wfile.write(body)

        def _local_request(self) -> bool:
            port = cast(tuple[str, int], self.server.server_address)[1]
            allowed_hosts = {f"127.0.0.1:{port}", f"localhost:{port}"}
            origin = self.headers.get("Origin")
            return self.headers.get("Host") in allowed_hosts and (
                origin is None or origin in {f"http://{host}" for host in allowed_hosts}
            )

        def do_GET(self) -> None:
            if not self._local_request():
                self._send(403, b"Local requests only", "text/plain")
                return
            path = urlsplit(self.path).path
            if path in STATIC_FILES:
                filename, content_type = STATIC_FILES[path]
                self._send(200, (ASSETS / filename).read_bytes(), content_type)
            elif path in {"/api/snapshot", "/api/demo"}:
                self._snapshot(path == "/api/demo")
            else:
                self._send(404, b"Not found", "text/plain")

        def _snapshot(self, demo: bool) -> None:
            try:
                payload = demo_snapshot() if demo else cache.get()
            except (OSError, ValueError, SessionMetadataError):
                self._send(
                    503,
                    b'{"error":"The local Hub snapshot could not be read. Check the registry and metadata files, then retry."}',
                    "application/json",
                )
                return
            self._send(200, json.dumps(payload).encode("utf-8"), "application/json")

    return ThreadingHTTPServer(("127.0.0.1", port), Handler)


def serve(registry_path: str | None, port: int = 8765) -> int:
    """Run until interrupted; no browser, agent control or network relay is started."""
    server = create_server(registry_path, port)
    print(
        f"Agent workspace: http://127.0.0.1:{server.server_address[1]} (Ctrl+C to stop)",
        flush=True,
    )
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0
