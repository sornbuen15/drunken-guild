"""Small durable job queue for explicitly submitted Claude and Codex work.

Only Guild-owned processes and worktrees are controlled. Existing desktop/terminal
sessions are never adopted or inferred from process names. No transcripts or
reasoning blocks are ingested; monitoring retains task metadata and final output.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .codex_threads import CodexThreadObserver
from .paths import secure_file
from .redact import redact

PROVIDERS = {"Claude Code": "claude", "Codex": "codex"}
TERMINAL = {"completed", "failed", "cancelled", "interrupted", "needs_attention"}
MAX_JOBS = 200
MAX_OUTPUT = 32000


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def clean(value: Any, limit: int = 240) -> str:
    return redact(value)[:limit] if isinstance(value, str) else ""


def _claude_tool(job: dict[str, Any], parent: Any, block: dict[str, Any]) -> None:
    children = job["children"]
    tool = clean(block.get("name"))
    target = children.get(parent, job) if isinstance(parent, str) else job
    target["activity"] = tool
    if tool in {"Agent", "Task"}:
        child_id = clean(block.get("id"))
        inputs = block.get("input", {})
        if child_id and isinstance(inputs, dict) and len(children) < 128:
            children[child_id] = {
                "id": child_id,
                "parent_id": parent,
                "task": clean(inputs.get("description")) or "Task not reported",
                "role": clean(inputs.get("subagent_type")),
                "status": "running",
                "activity": "starting",
            }


def _observe_claude(job: dict[str, Any], event: dict[str, Any]) -> None:
    if isinstance(event.get("session_id"), str):
        job["session_id"] = event["session_id"]
    message = event.get("message", {})
    blocks = message.get("content", []) if isinstance(message, dict) else []
    for block in blocks if isinstance(blocks, list) else []:
        if not isinstance(block, dict):
            continue
        if block.get("type") == "tool_use":
            _claude_tool(job, event.get("parent_tool_use_id"), block)
        elif block.get("type") == "tool_result":
            child = job["children"].get(block.get("tool_use_id"))
            if child:
                child["status"] = "failed" if block.get("is_error") else "completed"
    if event.get("type") == "result":
        job["result"] = clean(event.get("result"), MAX_OUTPUT)
        job["agent_error"] = bool(event.get("is_error"))
        job["needs_attention"] = bool(event.get("permission_denials"))
        job["activity"] = "turn finished"
    if event.get("subtype") == "permission_denied":
        job["needs_attention"] = True


def _codex_children(job: dict[str, Any], item: dict[str, Any]) -> None:
    ids = item.get("receiver_thread_ids", [])
    if not isinstance(ids, list):
        return
    for child_id in ids[:32]:
        if not isinstance(child_id, str) or len(job["children"]) >= 128:
            continue
        child = job["children"].setdefault(
            child_id,
            {
                "id": child_id,
                "parent_id": item.get("sender_thread_id"),
                "task": clean(item.get("prompt")) or "Task not reported",
                "status": "unknown",
                "activity": "not reported",
            },
        )
        states = item.get("agents_states", {})
        reported = states.get(child_id, {}) if isinstance(states, dict) else {}
        child["status"] = (
            clean(reported.get("status")) if isinstance(reported, dict) else "unknown"
        )
        child["activity"] = clean(item.get("tool")) or "not reported"


def _observe_codex(job: dict[str, Any], event: dict[str, Any]) -> None:
    kind = event.get("type")
    if kind == "thread.started":
        job["session_id"] = clean(event.get("thread_id"))
    item = event.get("item", {})
    if isinstance(item, dict):
        item_type = item.get("type")
        if isinstance(item_type, str):
            job["activity"] = clean(item_type)
        if kind == "item.completed" and item_type == "agent_message":
            job["result"] = clean(item.get("text"), MAX_OUTPUT)
        if item_type in {"collab_tool_call", "collab_agent_tool_call"}:
            _codex_children(job, item)
    if kind in {"error", "turn.failed"}:
        job["agent_error"] = True
        error = event.get("error", {})
        job["result"] = clean(event.get("message"), MAX_OUTPUT) or clean(
            error.get("message") if isinstance(error, dict) else "Agent turn failed",
            MAX_OUTPUT,
        )


def observe(job: dict[str, Any], provider: str, event: dict[str, Any]) -> None:
    """Project allowlisted stream fields into a task tree; discard raw events."""
    job["observed_at"] = now()
    job.setdefault("children", {})
    if provider == "Claude Code":
        _observe_claude(job, event)
    else:
        _observe_codex(job, event)


def stop_process(process: subprocess.Popen[str]) -> None:
    """Stop only this owned, still-running process tree."""
    if process.poll() is not None:
        return
    if sys.platform == "win32":
        killer = shutil.which("taskkill")
        if killer:
            subprocess.run(
                [killer, "/PID", str(process.pid), "/T", "/F"],
                capture_output=True,
                timeout=10,
                check=False,
            )
        else:
            process.terminate()
    else:
        os.killpg(process.pid, signal.SIGTERM)
    try:
        process.wait(timeout=10)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=5)


class JobManager:
    """One worker, bounded persistent history and idempotent submissions."""

    def __init__(
        self, state_dir: Path, projects: dict[str, Path], *, start_worker: bool = True
    ) -> None:
        self.root = state_dir.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        secure_file(self.root)
        self.file = self.root / "jobs.json"
        self.projects = {key: value.resolve() for key, value in projects.items()}
        self.lock = threading.RLock()
        self.wake = threading.Event()
        self.stopping = threading.Event()
        self.active: subprocess.Popen[str] | None = None
        self.active_id: str | None = None
        self.jobs: list[dict[str, Any]] = []
        if self.file.exists():
            if self.file.stat().st_size > 20_000_000:
                raise ValueError("Job history exceeds size limit")
            self.jobs = json.loads(self.file.read_text(encoding="utf-8"))
            if not isinstance(self.jobs, list) or not all(
                isinstance(j, dict) for j in self.jobs
            ):
                raise ValueError("Invalid job history")
            for job in self.jobs:
                if job.get("status") not in TERMINAL:
                    job.update(
                        status="interrupted",
                        activity="Server restarted; submit a follow-up to continue",
                    )
            self._save()
        self.worker = threading.Thread(
            target=self._loop, daemon=True, name="guild-jobs"
        )
        if start_worker:
            self.worker.start()

    def _save(self) -> None:
        temporary = self.root / "jobs.next.json"
        temporary.touch(exist_ok=True)
        secure_file(temporary)
        temporary.write_text(
            json.dumps(self.jobs, ensure_ascii=False), encoding="utf-8"
        )
        temporary.replace(self.file)

    def snapshot(self) -> list[dict[str, Any]]:
        with self.lock:
            return json.loads(json.dumps(self.jobs))  # type: ignore[no-any-return]

    def _validate(self, data: dict[str, Any]) -> tuple[str, str, str, str]:
        project = data.get("project_id")
        provider = data.get("provider")
        prompt = data.get("prompt")
        request_id = data.get("request_id")
        if not isinstance(project, str) or project not in self.projects:
            raise ValueError("Select a registered project")
        if not isinstance(provider, str) or provider not in PROVIDERS:
            raise ValueError("Select Claude Code or Codex")
        if not isinstance(prompt, str) or not prompt.strip() or len(prompt) > 12000:
            raise ValueError("Enter a task of 1 to 12000 characters")
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 100:
            raise ValueError("A request ID is required")
        if not self.projects[project].is_dir():
            raise ValueError("The project directory is unavailable")
        return project, provider, prompt, request_id

    def submit(self, data: dict[str, Any]) -> dict[str, Any]:
        project, provider, prompt, request_id = self._validate(data)
        parent_id = data.get("parent_id") or None
        with self.lock:
            for existing in self.jobs:
                if existing["request_id"] == request_id:
                    if any(
                        existing[key] != value
                        for key, value in (
                            ("prompt", prompt.strip()),
                            ("project_id", project),
                            ("provider", provider),
                            ("parent_id", parent_id),
                        )
                    ):
                        raise ValueError("This request ID belongs to a different task")
                    return dict(existing)
            if len(self.jobs) >= MAX_JOBS:
                raise ValueError(
                    "Job history is full; archive it before accepting more work"
                )
            if sum(job["status"] not in TERMINAL for job in self.jobs) >= 10:
                raise ValueError("The queue is full")
            parent = next((job for job in self.jobs if job["id"] == parent_id), None)
            if parent_id and (
                not parent
                or parent["provider"] != provider
                or parent["project_id"] != project
            ):
                raise ValueError("Follow-up must use the same project and agent")
            if parent and (
                parent["status"] not in TERMINAL or not parent.get("session_id")
            ):
                raise ValueError(
                    "Wait for the previous task to finish with a resumable session"
                )
            if parent and any(
                j["status"] not in TERMINAL
                and j.get("workspace") == parent.get("workspace")
                for j in self.jobs
            ):
                raise ValueError("This workspace already has queued or active work")
            job: dict[str, Any] = {
                "id": secrets.token_hex(8),
                "request_id": request_id,
                "project_id": project,
                "provider": provider,
                "prompt": prompt.strip(),
                "parent_id": parent_id,
                "session_id": parent.get("session_id") if parent else None,
                "workspace": parent.get("workspace") if parent else None,
                "status": "queued",
                "activity": "waiting for worker",
                "children": {},
                "subagent_coverage": "pending" if provider == "Codex" else "stream",
                "created_at": now(),
                "observed_at": None,
                "result": "",
                "diagnostic": "",
            }
            self.jobs.append(job)
            self._save()
            self.wake.set()
            return dict(job)

    def cancel(self, job_id: str) -> dict[str, Any]:
        with self.lock:
            job = next((j for j in self.jobs if j["id"] == job_id), None)
            if job is None:
                raise ValueError("Unknown job")
            if job["status"] in TERMINAL:
                return dict(job)
            job.update(
                status="cancelled", activity="Cancellation requested", observed_at=now()
            )
            process = self.active if self.active_id == job_id else None
            self._save()
        if process is not None:
            stop_process(process)
        return dict(job)

    def _workspace(self, job: dict[str, Any]) -> Path:
        if job.get("workspace"):
            workspace = Path(job["workspace"]).resolve()
            if (
                not workspace.is_relative_to(self.root / "worktrees")
                or not workspace.is_dir()
            ):
                raise ValueError("Managed workspace is unavailable")
            return workspace
        git = shutil.which("git")
        if git is None:
            raise ValueError("Git is required for an isolated task workspace")
        project = self.projects[job["project_id"]]
        workspace = self.root / "worktrees" / str(job["id"])
        workspace.parent.mkdir(exist_ok=True)
        result = subprocess.run(
            [
                git,
                "-C",
                str(project),
                "worktree",
                "add",
                "-b",
                f"codex/guild-{job['id']}",
                str(workspace),
                "HEAD",
            ],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=60,
            check=False,
        )
        if result.returncode:
            raise ValueError(
                "Could not create task worktree: " + clean(result.stderr, 1500)
            )
        with self.lock:
            job["workspace"] = str(workspace)
            self._save()
        return workspace

    def _loop(self) -> None:
        while not self.stopping.is_set():
            with self.lock:
                job = next((j for j in self.jobs if j["status"] == "queued"), None)
                if job:
                    job.update(
                        status="running",
                        activity="Preparing isolated workspace",
                        observed_at=now(),
                    )
                    self._save()
            if job is None:
                self.wake.wait(1)
                self.wake.clear()
                continue
            try:
                self._run(job)
            except (OSError, ValueError, subprocess.SubprocessError) as exc:
                with self.lock:
                    if job["status"] != "cancelled":
                        job.update(
                            status="failed",
                            diagnostic=clean(str(exc), 4000),
                            observed_at=now(),
                        )
                    self._save()
            finally:
                with self.lock:
                    self.active = None
                    self.active_id = None

    def _read_output(self, job: dict[str, Any], process: subprocess.Popen[str]) -> None:
        assert process.stdout is not None
        while line := process.stdout.readline(65536):
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                with self.lock:
                    job["diagnostic"] = (job["diagnostic"] + clean(line, 1000))[-4000:]
                continue
            if isinstance(event, dict):
                with self.lock:
                    observe(job, job["provider"], event)
        process.stdout.close()

    def _sync_codex_children(
        self, job: dict[str, Any], observer: CodexThreadObserver
    ) -> None:
        with self.lock:
            thread_id = job.get("session_id")
        if not isinstance(thread_id, str) or not thread_id:
            return
        children = observer.children(thread_id)
        with self.lock:
            for child in children:
                job["children"][child["id"]] = child
            job["subagent_coverage"] = "available"
            self._save()

    def _probe_codex_children(
        self,
        job: dict[str, Any],
        observer: CodexThreadObserver | None,
        executable: str,
    ) -> tuple[CodexThreadObserver | None, bool]:
        with self.lock:
            has_thread = bool(job.get("session_id"))
        if not has_thread:
            return observer, False
        try:
            if observer is None:
                observer = CodexThreadObserver(executable)
            self._sync_codex_children(job, observer)
        except (OSError, ValueError) as exc:
            with self.lock:
                job["subagent_coverage"] = "unavailable"
                job["diagnostic"] = clean(str(exc), 4000)
                self._save()
            return observer, True
        return observer, False

    def _interrupt_job(
        self, job: dict[str, Any], process: subprocess.Popen[str]
    ) -> None:
        stop_process(process)
        with self.lock:
            if job["status"] != "cancelled":
                job.update(
                    status="interrupted",
                    activity="Worker stopped or runtime limit reached",
                )

    def _finish_job(self, job: dict[str, Any], process: subprocess.Popen[str]) -> None:
        with self.lock:
            if job["status"] not in TERMINAL:
                status = (
                    "needs_attention"
                    if job.get("needs_attention")
                    else "failed"
                    if process.returncode or job.get("agent_error")
                    else "completed"
                )
                job.update(status=status, activity=status)
            job.update(exit_code=process.returncode, observed_at=now())
            self._save()

    def _run(self, job: dict[str, Any]) -> None:
        executable = shutil.which(PROVIDERS[job["provider"]])
        if executable is None:
            raise ValueError("Agent CLI not found on the server PATH")
        workspace = self._workspace(job)
        session = job.get("session_id")
        if job["provider"] == "Codex":
            command = [executable, "exec", "--json", "--sandbox", "workspace-write"]
            command += ["resume", session, "-"] if session else ["-"]
        else:
            command = [
                executable,
                "-p",
                "--verbose",
                "--output-format",
                "stream-json",
                "--permission-mode",
                "default",
            ]
            if session:
                command += ["--resume", session]
        instruction = (
            "Work only on the assigned task in this isolated worktree. Follow AGENTS.md. "
            "Do not commit, push, merge, deploy, install packages or weaken permission controls. "
            "Report changed files, checks and unresolved blockers.\n\n" + job["prompt"]
        )
        with self.lock:
            if job["status"] == "cancelled" or self.stopping.is_set():
                return
            process = subprocess.Popen(
                command,
                cwd=workspace,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                start_new_session=os.name != "nt",
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            self.active = process
            self.active_id = job["id"]
            job.update(activity="Agent started", observed_at=now())
            self._save()
        assert process.stdin is not None and process.stdout is not None
        process.stdin.write(instruction)
        process.stdin.close()

        reader = threading.Thread(
            target=self._read_output, args=(job, process), daemon=True
        )
        reader.start()
        deadline = time.monotonic() + 1800
        observer: CodexThreadObserver | None = None
        monitor_failed = False
        last_probe = 0.0
        try:
            while process.poll() is None:
                if (
                    job["provider"] == "Codex"
                    and not monitor_failed
                    and time.monotonic() - last_probe >= 10
                ):
                    last_probe = time.monotonic()
                    observer, monitor_failed = self._probe_codex_children(
                        job, observer, executable
                    )
                if self.stopping.wait(1) or time.monotonic() >= deadline:
                    self._interrupt_job(job, process)
                    break
            reader.join(timeout=5)
            if job["provider"] == "Codex" and not monitor_failed:
                observer, _ = self._probe_codex_children(job, observer, executable)
        finally:
            if observer is not None:
                observer.close()
        self._finish_job(job, process)

    def close(self) -> None:
        self.stopping.set()
        self.wake.set()
        with self.lock:
            process = self.active
        if process:
            stop_process(process)
        if self.worker.is_alive():
            self.worker.join(timeout=15)
