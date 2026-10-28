"""Loopback-only, read-only browser view of the existing local Hub sources."""

from __future__ import annotations

import json
import secrets
import shutil
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from time import monotonic
from typing import Any, cast
from urllib.parse import urlsplit

from . import hub, paths
from .guild_jobs import JobManager
from .registry import ProjectRegistry
from .session_store import SessionMetadataError

ASSETS = Path(__file__).with_name("dashboard")
STATIC_FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/jobs.js": ("jobs.js", "text/javascript; charset=utf-8"),
    "/app.js": ("app.js", "text/javascript; charset=utf-8"),
    "/style.css": ("style.css", "text/css; charset=utf-8"),
}


def agent_inventory() -> list[dict[str, str]]:
    """Find known CLI entry points on this process PATH without launching agents.

    Absence from PATH is not evidence that a tool is absent from the machine.
    CLI availability is independent of session discovery and authentication.
    """
    return [
        {
            "provider": provider,
            "command": command,
            "cli_status": "found" if shutil.which(command) else "not_found",
        }
        for provider, command in (
            ("Claude Code", "claude"),
            ("Codex", "codex"),
            ("Aider", "aider"),
            ("Antigravity", "agy"),
        )
    ]


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
    inventory = agent_inventory()
    for tool in inventory:
        source = next(
            (item for item in sources if item["provider"] == tool["provider"]), None
        )
        if source is None:
            source = {
                "provider": tool["provider"],
                "status": "unsupported",
                "session_count": None,
                "observed_at": None,
            }
            sources.append(source)
        source.update(tool)
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
                "cli_status": "found",
                "command": "claude",
                "status": "available",
                "session_count": 2,
                "observed_at": now,
            },
            {
                "provider": "Codex",
                "cli_status": "found",
                "command": "codex",
                "status": "unsupported",
                "session_count": None,
                "observed_at": None,
            },
            {
                "provider": "Aider",
                "cli_status": "found",
                "command": "aider",
                "status": "unsupported",
                "session_count": None,
                "observed_at": None,
            },
            {
                "provider": "Antigravity",
                "cli_status": "not_found",
                "command": "agy",
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


def create_server(
    registry_path: str | None,
    port: int = 8765,
    *,
    jobs: JobManager | None = None,
    web_origin: str | None = None,
    web_user: str | None = None,
) -> ThreadingHTTPServer:
    """Bind only to IPv4 loopback and reject foreign browser origins/Host values."""

    cache = _SnapshotCache(registry_path)
    csrf_token = secrets.token_urlsafe(32)
    if bool(web_origin) != bool(web_user):
        raise ValueError(
            "Remote access requires both an HTTPS origin and an allowed Tailscale user"
        )
    remote = urlsplit(web_origin or "")
    if web_origin and (
        remote.scheme != "https"
        or not remote.hostname
        or remote.path
        or remote.query
        or remote.fragment
        or remote.username
    ):
        raise ValueError(
            "Remote origin must be an HTTPS origin without a path or credentials"
        )

    server = _GuildServer(("127.0.0.1", port), _Handler)
    server.jobs = jobs
    server.web_origin = web_origin
    server.web_user = web_user
    server.remote_host = remote.netloc
    server.csrf_token = csrf_token
    server.cache = cache
    return server


class _GuildServer(ThreadingHTTPServer):
    jobs: JobManager | None
    web_origin: str | None
    web_user: str | None
    remote_host: str
    csrf_token: str
    cache: _SnapshotCache


class _Handler(BaseHTTPRequestHandler):
    @property
    def hub(self) -> _GuildServer:
        return cast(_GuildServer, self.server)

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
        host = self.headers.get("Host")
        if host in allowed_hosts and (
            origin is None or origin in {f"http://{item}" for item in allowed_hosts}
        ):
            return True
        return bool(
            self.hub.web_origin
            and host == self.hub.remote_host
            and (origin is None or origin == self.hub.web_origin)
            and self.headers.get("Tailscale-User-Login") == self.hub.web_user
        )

    def do_GET(self) -> None:
        if not self._local_request():
            self._send(403, b"Local requests only", "text/plain")
            return
        path = urlsplit(self.path).path
        if path == "/api/jobs":
            self._json(
                200,
                {
                    "enabled": self.hub.jobs is not None,
                    "csrf_token": self.hub.csrf_token if self.hub.jobs else None,
                    "projects": list(self.hub.jobs.projects) if self.hub.jobs else [],
                    "providers": [
                        tool
                        for tool in agent_inventory()
                        if tool["provider"] in {"Claude Code", "Codex"}
                    ],
                    "jobs": self.hub.jobs.snapshot() if self.hub.jobs else [],
                },
            )
        elif path in STATIC_FILES:
            filename, content_type = STATIC_FILES[path]
            self._send(200, (ASSETS / filename).read_bytes(), content_type)
        elif path in {"/api/snapshot", "/api/demo"}:
            self._snapshot(path == "/api/demo")
        else:
            self._send(404, b"Not found", "text/plain")

    def _json(self, status: int, payload: dict[str, Any]) -> None:
        self._send(status, json.dumps(payload).encode("utf-8"), "application/json")

    def do_POST(self) -> None:
        self.connection.settimeout(5)
        if (
            not self._local_request()
            or not self.headers.get("Origin")
            or not secrets.compare_digest(
                self.headers.get("X-Guild-Token", ""), self.hub.csrf_token
            )
        ):
            self._json(
                403, {"error": "Reload the Guild page and submit from that page"}
            )
            return
        if self.hub.jobs is None:
            self._json(403, {"error": "Job control is not enabled on this server"})
            return
        if self.headers.get_content_type() != "application/json":
            self._json(415, {"error": "Expected JSON"})
            return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if not 0 < length <= 65536 or self.headers.get("Transfer-Encoding"):
                raise ValueError("Invalid request size")
            data = json.loads(self.rfile.read(length))
            if not isinstance(data, dict):
                raise ValueError("Expected a JSON object")
            route = urlsplit(self.path).path
            if route == "/api/jobs":
                self._json(202, {"job": self.hub.jobs.submit(data)})
            elif route.startswith("/api/jobs/") and route.endswith("/cancel"):
                self._json(200, {"job": self.hub.jobs.cancel(route.split("/")[3])})
            else:
                self._json(404, {"error": "Unknown control action"})
        except (ValueError, UnicodeDecodeError) as exc:
            self._json(400, {"error": str(exc)})
        except OSError:
            self._json(
                503, {"error": "Job state could not be saved or request timed out"}
            )

    def _snapshot(self, demo: bool) -> None:
        try:
            payload = demo_snapshot() if demo else self.hub.cache.get()
        except (OSError, ValueError, SessionMetadataError):
            self._send(
                503,
                b'{"error":"The local Hub snapshot could not be read. Check the registry and metadata files, then retry."}',
                "application/json",
            )
            return
        self._send(200, json.dumps(payload).encode("utf-8"), "application/json")


def serve(
    registry_path: str | None,
    port: int = 8765,
    *,
    control: bool = False,
    jobs_dir: str | None = None,
    web_origin: str | None = None,
    web_user: str | None = None,
) -> int:
    """Run until interrupted; no browser, agent control or network relay is started."""
    jobs = None
    if control:
        registry = (
            ProjectRegistry(registry_path) if registry_path else ProjectRegistry()
        )
        projects = {}
        for project_id in registry.project_ids():
            config = registry.get_project_config(project_id)
            if config.path:
                projects[project_id] = Path(config.path)
        state_dir = Path(jobs_dir) if jobs_dir else paths.ensure_home() / "guild-jobs"
        jobs = JobManager(state_dir, projects)
    try:
        server = create_server(
            registry_path, port, jobs=jobs, web_origin=web_origin, web_user=web_user
        )
    except (OSError, ValueError):
        if jobs:
            jobs.close()
        raise
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
        if jobs:
            jobs.close()
    return 0
