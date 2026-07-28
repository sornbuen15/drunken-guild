import asyncio
import json
import os
import sys
from typing import Any

import discord

from core.registry import ProjectRegistry
from service.discord_runner import RAW_LOG_FILE, AgentRunner
from service.discord_utils import find_config, log_activity

DISCORD_MESSAGE_LIMIT = 2000
LIST_COMMAND_MAX_ITEMS = 8
DEFAULT_TARGET_PROJECT = "drunken-team"

# Absolute paths so these resolve correctly regardless of which directory a
# subprocess is launched with as its cwd (e.g. a non-default target project).
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
JIRA_BRIDGE_SCRIPT = os.path.join(_REPO_ROOT, "scripts", "jira_bridge.py")
QA_AUTOMATION_SCRIPT = os.path.join(_REPO_ROOT, "scripts", "qa_automation.py")

JIRA_LIST_COMMANDS = {
    "/tasks": ("get-todo", "To Do"),
    "/inprogress": ("get-in-progress", "In Progress"),
    "/review": ("get-in-review", "In Review"),
    "/backlog": ("get-backlog", "Backlog"),
}

AGENTS_METADATA = {
    "principal-engineer": {
        "name": "Principal Eng",
        "job": "Archmage",
        "model": "Gemini 2.5 Pro",
        "description": "High-level architecture, design standards, task delegation, and codebase rules checker. Speaks like a wise wizard, loves beer and lager.",
    },
    "devops-engineer": {
        "name": "DevOps Eng",
        "job": "Iron Knight",
        "model": "Gemini 2.5 Flash",
        "description": "Delivery pipelines, K8s orchestration, Docker, IaC. Speaks like an armored guardian, loves green IPAs and pipeline monitoring.",
    },
    "laravel-developer": {
        "name": "Laravel Dev",
        "job": "Alchemist",
        "model": "Gemini 2.5 Flash",
        "description": "PHP, Laravel, migrations, blade templates. Speaks like a potion brewer, loves Artisan commands and caching whiskey in Redis.",
    },
    "qa-engineer": {
        "name": "QA Eng",
        "job": "Ranger",
        "model": "Gemini 2.5 Flash",
        "description": "Testing, Cypress, E2E suites. Speaks like a sharp shooter, likes finding bugs and ordering 0, 9999, or -1 beers.",
    },
    "security-engineer": {
        "name": "Security Eng",
        "job": "Rogue",
        "model": "Gemini 2.5 Pro",
        "description": "Vulnerability scanning, secret detection. Speaks like a rogue hiding in shadows, likes encrypted rum and SQL injection menu cards.",
    },
    "voice-ai-specialist": {
        "name": "Voice Specialist",
        "job": "Bard",
        "model": "Gemini 2.5 Pro",
        "description": "Speech, WebRTC, Whisper. Speaks like a bard playing lute, singing sea shanties and audio tuning.",
    },
    "agentic-systems-specialist": {
        "name": "Agentic Specialist",
        "job": "Summoner",
        "model": "Gemini 2.5 Pro",
        "description": "Multi-agent coordination, workspaces. Speaks like a summoner controling subagents, using low-power screensaver mode.",
    },
    "fullstack-engineer": {
        "name": "Fullstack Eng",
        "job": "Spellsword",
        "model": "Gemini 2.5 Flash",
        "description": "Frontend, backend, CSS, responsive layout. Speaks like a dual-wielding warrior, struggling to center divs and styling with HSL colors.",
    },
}


async def _handle_detail_command(message: discord.Message) -> None:
    if os.path.exists(RAW_LOG_FILE) and os.path.getsize(RAW_LOG_FILE) > 0:
        try:
            await message.channel.send(
                content="Here is the raw execution log file, Boss:",
                file=discord.File(RAW_LOG_FILE),
            )
        except Exception as e:
            await message.channel.send(
                f"Agy failed to upload raw log file due to error: {e}"
            )
    else:
        await message.channel.send(
            "No raw execution history found in the system logs, Boss."
        )


async def _handle_stop_command(
    agent_runner: AgentRunner, message: discord.Message
) -> None:
    from service.discord_runner import kill_orphaned_agy_processes

    stopped_tracked = agent_runner.is_busy()
    if stopped_tracked:
        await agent_runner.cancel_current_task()

    # Also sweep the on-disk PID registry: if a previous daemon instance
    # crashed and was restarted (e.g. under launchd), a fresh AgentRunner
    # has no memory of a still-running child from before the crash.
    orphans_killed = kill_orphaned_agy_processes()

    if stopped_tracked or orphans_killed:
        parts = []
        if stopped_tracked:
            parts.append("the active agent task")
        if orphans_killed:
            parts.append(f"{len(orphans_killed)} orphaned process(es)")
        await message.channel.send(
            f"🛑 **Emergency Stop!** Terminated {' and '.join(parts)}."
        )
    else:
        await message.channel.send(
            "💤 No active agent task is being tracked right now — nothing to stop."
        )


def _truncate_for_discord(text: str) -> str:
    if len(text) <= DISCORD_MESSAGE_LIMIT:
        return text
    return text[: DISCORD_MESSAGE_LIMIT - 20] + "\n...(truncated)"


def _target_project_file() -> str | None:
    config_file = find_config()
    if not config_file:
        return None
    return os.path.join(os.path.dirname(config_file), "discord_target_project.json")


def _get_target_project() -> str:
    path = _target_project_file()
    if not path or not os.path.exists(path):
        return DEFAULT_TARGET_PROJECT
    try:
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
        return str(data.get("target_project") or DEFAULT_TARGET_PROJECT)
    except Exception:
        return DEFAULT_TARGET_PROJECT


def _set_target_project(name: str) -> None:
    path = _target_project_file()
    if not path:
        return
    with open(path, "w", encoding="utf-8") as f:
        json.dump({"target_project": name}, f)


def _target_project_cwd() -> str | None:
    """cwd to run project-scoped subprocesses (jira_bridge.py, gh) in for
    the currently selected target project. None means: use the daemon's
    own cwd (drunken-team, the default)."""
    name = _get_target_project()
    if name == DEFAULT_TARGET_PROJECT:
        return None
    proj = ProjectRegistry().get_project(name)
    return proj["path"] if proj else None


async def _run_jira_bridge_raw(
    args: list[str], cwd: str | None = None
) -> tuple[int, str, str]:
    """Run jira_bridge.py without blocking the event loop. sys.executable
    (not a bare "python") and an absolute script path so this resolves
    correctly regardless of the daemon's launchd-restricted PATH or which
    project's directory `cwd` points at -- the same class of bug DT-93
    found and fixed for `uv`/`ruff`/`mypy`/`pytest`."""
    proc = await asyncio.create_subprocess_exec(
        sys.executable,
        JIRA_BRIDGE_SCRIPT,
        *args,
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    return (
        proc.returncode or 0,
        stdout.decode("utf-8", errors="replace"),
        stderr.decode("utf-8", errors="replace").strip(),
    )


async def _run_jira_bridge(
    action: str, cwd: str | None = None
) -> tuple[list[dict[str, Any]], str | None]:
    """Run a read-only jira_bridge.py query action (get-todo, get-backlog, ...)."""
    code, stdout, stderr = await _run_jira_bridge_raw([action], cwd)
    if code != 0:
        return [], stderr or "unknown error"
    try:
        data = json.loads(stdout)
    except json.JSONDecodeError:
        return [], "failed to parse jira_bridge.py output"
    return (data if isinstance(data, list) else []), None


async def _transition_issue(
    issue_key: str, target_status: str, cwd: str | None = None
) -> tuple[bool, str]:
    code, stdout, stderr = await _run_jira_bridge_raw(
        ["transition", issue_key, target_status], cwd
    )
    if code != 0:
        return False, stderr or "unknown error"
    return True, stdout.strip()


def _format_issue_list(issues: list[dict[str, Any]], title: str) -> str:
    if not issues:
        return f"**{title}** (0)\n(no issues)"
    lines = [f"**{title}** ({len(issues)})"]
    for issue in issues[:LIST_COMMAND_MAX_ITEMS]:
        summary = (issue.get("summary") or "").strip()
        if len(summary) > 60:
            summary = summary[:57] + "..."
        priority = issue.get("priority") or "?"
        lines.append(f"`{issue.get('key')}` [{priority}] {summary}")
    remaining = len(issues) - LIST_COMMAND_MAX_ITEMS
    if remaining > 0:
        lines.append(f"...and {remaining} more (see CLI for the full list)")
    return _truncate_for_discord("\n".join(lines))


async def _handle_jira_list_command(
    message: discord.Message, action: str, title: str, cwd: str | None = None
) -> None:
    issues, error = await _run_jira_bridge(action, cwd)
    if error:
        await message.channel.send(f"⚠️ Couldn't fetch **{title}**: {error}")
        return
    await message.channel.send(_format_issue_list(issues, title))


async def _handle_pr_list_command(
    message: discord.Message, cwd: str | None = None
) -> None:
    proc = await asyncio.create_subprocess_exec(
        "gh",
        "pr",
        "list",
        "--state",
        "open",
        "--json",
        "number,title,url,isDraft",
        stdout=asyncio.subprocess.PIPE,
        stderr=asyncio.subprocess.PIPE,
        cwd=cwd,
    )
    stdout, stderr = await proc.communicate()
    if proc.returncode != 0:
        await message.channel.send(
            f"⚠️ Couldn't fetch open PRs: {stderr.decode('utf-8', errors='replace').strip()}"
        )
        return
    try:
        prs = json.loads(stdout.decode("utf-8"))
    except json.JSONDecodeError:
        await message.channel.send("⚠️ Couldn't parse `gh pr list` output.")
        return
    if not prs:
        await message.channel.send("**Open PRs** (0)\n(none open)")
        return
    lines = [f"**Open PRs** ({len(prs)})"]
    for pr in prs[:LIST_COMMAND_MAX_ITEMS]:
        draft = " (draft)" if pr.get("isDraft") else ""
        lines.append(f"#{pr.get('number')}{draft} {pr.get('title')} — {pr.get('url')}")
    remaining = len(prs) - LIST_COMMAND_MAX_ITEMS
    if remaining > 0:
        lines.append(f"...and {remaining} more")
    await message.channel.send(_truncate_for_discord("\n".join(lines)))


async def _handle_pending_command(
    approval_manager: Any, message: discord.Message
) -> None:
    if approval_manager is None:
        await message.channel.send("⚠️ Approval manager isn't wired up in this context.")
        return
    pending = approval_manager.list_pending()
    if not pending:
        await message.channel.send("✅ Nothing waiting on approval right now.")
        return
    lines = [f"**Pending approvals** ({len(pending)})"]
    for req in pending[:LIST_COMMAND_MAX_ITEMS]:
        action = (req["action"] or "").strip()
        if len(action) > 80:
            action = action[:77] + "..."
        marker = "⏸️ escalated" if req["status"] == "escalated" else "⏳ pending"
        lines.append(f"`{req['ticket_key']}` {marker} — {action}")
    remaining = len(pending) - LIST_COMMAND_MAX_ITEMS
    if remaining > 0:
        lines.append(f"...and {remaining} more")
    await message.channel.send(_truncate_for_discord("\n".join(lines)))


async def _try_handle_query_command(
    slash_cmd: str, message: discord.Message, approval_manager: Any
) -> bool:
    """Handles the read-only /tasks /inprogress /review /backlog /pr /pending
    group. Split out of _handle_slash_command to keep its branching under
    the McCabe complexity limit. Returns True if the command was handled."""
    if slash_cmd in JIRA_LIST_COMMANDS:
        action, title = JIRA_LIST_COMMANDS[slash_cmd]
        project = _get_target_project()
        display_title = (
            title if project == DEFAULT_TARGET_PROJECT else f"{title} ({project})"
        )
        await _handle_jira_list_command(
            message, action, display_title, _target_project_cwd()
        )
        return True
    if slash_cmd == "/pr":
        await _handle_pr_list_command(message, _target_project_cwd())
        return True
    if slash_cmd == "/pending":
        await _handle_pending_command(approval_manager, message)
        return True
    return False


async def _handle_project_command(message: discord.Message, content_str: str) -> None:
    parts = content_str.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        current = _get_target_project()
        await message.channel.send(
            f"📍 Target project ตอนนี้คือ **{current}**\n"
            "พิมพ์ `/project <name>` เพื่อสลับ (เช่น `/project beta`)"
        )
        return
    name = parts[1].strip()
    if name != DEFAULT_TARGET_PROJECT and not ProjectRegistry().get_project(name):
        known = ", ".join(sorted(ProjectRegistry().get_projects().keys()))
        await message.channel.send(f"⚠️ ไม่พบโปรเจกต์ `{name}` ที่ลงทะเบียนไว้ (มี: {known})")
        return
    _set_target_project(name)
    await message.channel.send(
        f"✅ สลับ target project ของ `/tasks` `/inprogress` `/review` `/backlog` "
        f"`/pr` `/next` `/refine` เป็น **{name}** แล้วค่ะ"
    )


async def _handle_next_command(message: discord.Message) -> None:
    cwd = _target_project_cwd()
    in_progress, error = await _run_jira_bridge("get-in-progress", cwd)
    if error:
        await message.channel.send(f"⚠️ เช็ค In Progress ไม่ได้: {error}")
        return
    if in_progress:
        keys = ", ".join(
            i.get("key", "?") for i in in_progress[:LIST_COMMAND_MAX_ITEMS]
        )
        await message.channel.send(
            f"🚧 มีงาน In Progress ค้างอยู่แล้ว: {keys}\nต้องปิดงานนี้ให้เสร็จก่อนถึงจะหยิบงานใหม่ได้ค่ะ"
        )
        return
    todo, error = await _run_jira_bridge("get-todo", cwd)
    if error:
        await message.channel.send(f"⚠️ เช็ค To Do ไม่ได้: {error}")
        return
    if not todo:
        await message.channel.send("✅ ไม่มีงานเหลือใน To Do แล้วค่ะ")
        return
    top = todo[0]
    key = top.get("key", "?")
    ok, detail = await _transition_issue(key, "In Progress", cwd)
    if not ok:
        await message.channel.send(f"⚠️ Transition `{key}` ไม่สำเร็จ: {detail}")
        return
    summary = (top.get("summary") or "").strip()
    await message.channel.send(
        _truncate_for_discord(f"▶️ **{key}** ถูกย้ายไป In Progress แล้วค่ะ\n{summary}")
    )


def _build_refine_report(
    backlog: list[dict[str, Any]],
    critical: list[dict[str, Any]],
    promoted: list[str],
    failed: list[str],
) -> str:
    by_priority: dict[str, list[str]] = {}
    for issue in backlog:
        if issue in critical:
            continue
        p = issue.get("priority") or "Unknown"
        by_priority.setdefault(p, []).append(issue.get("key", "?"))

    lines = [f"**Backlog refinement** ({len(backlog)} total)"]
    if promoted:
        lines.append(f"🔺 Auto-promoted Critical -> To Do: {', '.join(promoted)}")
    if failed:
        lines.append(f"⚠️ Promote ไม่สำเร็จ: {', '.join(failed)}")
    for priority in ("High", "Medium", "Low", "Unknown"):
        keys = by_priority.get(priority)
        if not keys:
            continue
        shown = ", ".join(keys[:LIST_COMMAND_MAX_ITEMS])
        extra = (
            f" +{len(keys) - LIST_COMMAND_MAX_ITEMS} more"
            if len(keys) > LIST_COMMAND_MAX_ITEMS
            else ""
        )
        lines.append(f"**{priority}** ({len(keys)}): {shown}{extra}")
    lines.append("*(ใช้ CLI `/refine` เต็มรูปถ้าต้องการ promote กลุ่มอื่นเพิ่ม)*")
    return _truncate_for_discord("\n".join(lines))


async def _handle_refine_command(message: discord.Message) -> None:
    cwd = _target_project_cwd()
    backlog, error = await _run_jira_bridge("get-backlog", cwd)
    if error:
        await message.channel.send(f"⚠️ เช็ค Backlog ไม่ได้: {error}")
        return
    if not backlog:
        await message.channel.send("✅ Backlog ว่างค่ะ ไม่มีอะไรต้อง refine")
        return

    critical = [i for i in backlog if (i.get("priority") or "").lower() == "critical"]
    promoted = []
    failed = []
    for issue in critical:
        key = issue.get("key", "?")
        ok, detail = await _transition_issue(key, "To Do", cwd)
        if ok:
            promoted.append(key)
        else:
            failed.append(f"{key} ({detail})")

    await message.channel.send(
        _build_refine_report(backlog, critical, promoted, failed)
    )


async def _handle_approve_command(
    agent_runner: AgentRunner,
    approval_manager: Any,
    message: discord.Message,
    content_str: str,
) -> None:
    parts = content_str.split(None, 1)
    if len(parts) < 2 or not parts[1].strip():
        await message.channel.send("⚠️ ใช้แบบนี้ค่ะ: `/approve <ticket-key>`")
        return
    ticket_key = parts[1].strip().split()[0]
    if approval_manager is None:
        await message.channel.send("⚠️ Approval manager isn't wired up in this context.")
        return
    req = approval_manager.clear_escalated(ticket_key)
    if not req:
        await message.channel.send(
            f"⚠️ ไม่พบ escalated request ที่ค้างอยู่สำหรับ `{ticket_key}`"
        )
        return

    await message.channel.send(
        f"✅ เคลียร์ block ของ **{ticket_key}** แล้วค่ะ กำลังสั่งงานต่อ..."
    )
    prompt = (
        f"Ticket {ticket_key} was previously paused awaiting approval for: "
        f"{req.action} -- {req.reason}. The Boss has now approved this via "
        f"/approve on Discord. Read the ticket {ticket_key} and its comments "
        "for full context (including why it was paused), then continue the work."
    )
    meta = AGENTS_METADATA["fullstack-engineer"]
    escaped_prompt = prompt + _build_agent_suffix(meta)
    cmd_args = [
        "agy",
        "--dangerously-skip-permissions",
        "--new-project",
        "--print",
        escaped_prompt,
    ]
    asyncio.create_task(
        agent_runner.run_command_async(
            message.channel,
            message.author.mention,
            prompt,
            cmd_args,
            meta["name"],
        )
    )


async def _run_qa_gate_and_reply(
    message: discord.Message, ack_msg: discord.Message
) -> None:
    # This runs via asyncio.create_task (fire-and-forget) from
    # _handle_qa_command, so anything raised here has nowhere else to go --
    # without this try/except a crash here is completely silent (no Discord
    # reply, no log line, nothing). Always produce a reply.
    report_path: str | None = None
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            QA_AUTOMATION_SCRIPT,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            cwd=_REPO_ROOT,
        )
        stdout, stderr = await proc.communicate()
        output = stdout.decode("utf-8", errors="replace").strip()
        # qa_automation.py prints this marker line on its own when the
        # round-integration test generated an HTML report -- pull it out so
        # it doesn't show up as noise in the text reply itself.
        report_marker = "QA_HTML_REPORT_PATH:"
        output_lines = []
        for line in output.splitlines():
            if line.startswith(report_marker):
                report_path = line[len(report_marker) :].strip()
            else:
                output_lines.append(line)
        output = "\n".join(output_lines).strip()
        if proc.returncode != 0:
            err = stderr.decode("utf-8", errors="replace").strip()
            text = f"⚠️ **QA gate errored.**\n```\n{err[-1200:]}\n```"
        elif not output:
            text = "✅ **QA gate finished.** No output (nothing in review, or nothing passed)."
        else:
            text = f"🏁 **QA gate finished**\n```\n{output[-1500:]}\n```"
    except Exception as e:
        text = f"⚠️ **QA gate crashed before finishing.**\n```\n{e!r}\n```"
    text = _truncate_for_discord(text)
    has_report = bool(report_path and os.path.exists(report_path))

    def _file_kwargs() -> dict[str, Any]:
        # A fresh discord.File each attempt -- the underlying handle is
        # consumed after one send, so the fallback below needs its own copy
        # rather than reusing an already-sent File object.
        if not has_report:
            return {}
        assert report_path is not None
        return {"file": discord.File(report_path, filename="qa_report.html")}

    try:
        await ack_msg.reply(text, **_file_kwargs())
    except Exception:
        await message.channel.send(text, **_file_kwargs())


async def _handle_qa_command(message: discord.Message) -> None:
    ack = await message.channel.send(
        "🔍 **Running the QA round-integration gate...** จะ reply กลับที่ข้อความนี้เมื่อเสร็จค่ะ "
        "(อาจใช้เวลาสักครู่ -- รัน pytest/ruff/mypy เต็มรูปแบบ)"
    )
    asyncio.create_task(_run_qa_gate_and_reply(message, ack))


async def _try_handle_workflow_command(
    slash_cmd: str,
    content_str: str,
    agent_runner: AgentRunner,
    approval_manager: Any,
    message: discord.Message,
) -> bool:
    """Handles /project /next /refine /approve /qa. Split out of
    _handle_slash_command to keep its branching under the McCabe complexity
    limit. Returns True if the command was handled."""
    if slash_cmd == "/project":
        await _handle_project_command(message, content_str)
        return True
    if slash_cmd == "/next":
        await _handle_next_command(message)
        return True
    if slash_cmd == "/refine":
        await _handle_refine_command(message)
        return True
    if slash_cmd == "/approve":
        await _handle_approve_command(
            agent_runner, approval_manager, message, content_str
        )
        return True
    if slash_cmd == "/qa":
        await _handle_qa_command(message)
        return True
    return False


async def _handle_status_command(
    agent_runner: AgentRunner, message: discord.Message
) -> None:
    if not agent_runner.is_busy():
        await message.channel.send(
            "💤 **Workspace Status: IDLE**\nThe guild hall is quiet. No active quests."
        )
        return

    import glob
    import os

    logs = glob.glob("agy_discord_*_raw.log")
    if not logs:
        await message.channel.send(
            "🟢 **Workspace Status: BUSY**\n(Agent just dispatched, waiting for first log entry...)"
        )
        return

    latest_log = max(logs, key=os.path.getmtime)
    try:
        with open(latest_log, "r", encoding="utf-8") as f:
            lines = f.readlines()
        filtered = [
            line for line in lines if line.strip() not in ("<thinking>", "</thinking>")
        ]
        tail = "".join(filtered[-15:])
        if not tail.strip():
            tail = "(Just started or thinking deeply...)"
        await message.channel.send(
            f"🟢 **Workspace Status: BUSY**\nAn agent is currently active in the dungeon!\n**Latest Action:**\n```text\n{tail}\n```"
        )
    except Exception as e:
        await message.channel.send(
            f"🟢 **Workspace Status: BUSY**\n(Agent is running, but couldn't read log: {e})"
        )


async def _handle_slash_command(
    agent_runner: AgentRunner,
    message: discord.Message,
    content_str: str,
    approval_manager: Any = None,
) -> None:
    parts = content_str.split(None, 1)
    slash_cmd = parts[0].lower()
    if await _try_handle_query_command(slash_cmd, message, approval_manager):
        return
    if await _try_handle_workflow_command(
        slash_cmd, content_str, agent_runner, approval_manager, message
    ):
        return
    if slash_cmd == "/help":
        help_text = (
            "Hello, Boss! 🚀 Agy, your system router, welcomes you to the **Antigravity Workspace**!\n"
            "I coordinate tasks in the backroom office so you don't have to wait. Grab a pint of ale and relax!\n\n"
            "**Available Commands:**\n"
            "   - `/help` : Show this help menu.\n"
            "   - `/list-cmd` : View list of fast executable system commands.\n"
            "   - `/status` : Check the real-time status and logs of the active agent.\n"
            "   - `/stop` or `/kill` : Emergency stop all running agents instantly.\n"
            "   - `/tasks` : List Jira To Do issues.\n"
            "   - `/inprogress` : List Jira In Progress issues.\n"
            "   - `/review` : List Jira In Review issues.\n"
            "   - `/backlog` : List Jira backlog issues.\n"
            "   - `/pending` : List approval requests waiting on you.\n"
            "   - `/pr` : List open GitHub PRs.\n"
            "   - `/project [name]` : Show or switch the target project.\n"
            "   - `/next` : Pick up the top To Do issue -> In Progress.\n"
            "   - `/refine` : Auto-promote Critical backlog issues, report the rest.\n"
            "   - `/approve <ticket>` : Clear an escalated block and re-dispatch the work.\n"
            "   - `/qa` : Run the QA round-integration gate in the background.\n\n"
            "*(Note: Task creation and direct agent chatting via Discord is currently disabled. Please use the CLI.)*\n\n"
            "Agy is always waiting for your order at the counter! ⚡"
        )
        await message.channel.send(help_text)
        return
    elif slash_cmd == "/status":
        await _handle_status_command(agent_runner, message)
        return
    elif slash_cmd in ("/stop", "/kill"):
        await _handle_stop_command(agent_runner, message)
        return
    elif slash_cmd == "/list-cmd":
        list_text = (
            "Boss! Here is the menu of quick commands:\n"
            "1. `/status` : Check the real-time status and logs of the active agent.\n"
            "2. `/stop` or `/kill` : Emergency stop all running agents instantly.\n"
            "3. `/tasks` `/inprogress` `/review` `/backlog` : List Jira issues by lane.\n"
            "4. `/pending` : List approval requests waiting on you.\n"
            "5. `/pr` : List open GitHub PRs.\n"
            "6. `/project [name]` : Show or switch the target project.\n"
            "7. `/next` : Pick up the top To Do issue -> In Progress.\n"
            "8. `/refine` : Auto-promote Critical backlog issues, report the rest.\n"
            "9. `/approve <ticket>` : Clear an escalated block and re-dispatch the work.\n"
            "10. `/qa` : Run the QA round-integration gate in the background.\n\n"
            "You can type `/<command>` to execute it immediately!"
        )
        await message.channel.send(list_text)
        return
    await message.channel.send(
        "⚡ **Agy [System]:** คำสั่งนี้ถูกปิดใช้งานบน Discord แล้วค่ะ รบกวนสั่งงานผ่าน Terminal (CLI) แทนนะคะ ⚙️"
    )


def _parse_router_response(direct_response: str, content_str: str) -> dict[str, Any]:
    import re

    try:
        # Extract everything between the first { and the last }
        match = re.search(r"\{.*\}", direct_response, flags=re.DOTALL)
        if match:
            res = json.loads(match.group(0))
            return res if isinstance(res, dict) else {}
        # Fallback to pure json load
        fallback = json.loads(direct_response)
        return fallback if isinstance(fallback, dict) else {}
    except Exception as e:
        print(
            f"[Debug] Failed to parse router response: {direct_response} | Error: {e}",
            flush=True,
        )
        agy_match = re.search(r'"agy_response"\s*:\s*"([^"]+)', direct_response)
        agent_match = re.search(r'"target_agent"\s*:\s*"([^"]+)', direct_response)
        if agent_match:
            return {
                "is_task": True,
                "target_agent": agent_match.group(1),
                "refined_prompt": content_str,
            }
        elif agy_match:
            return {
                "is_task": False,
                "agy_response": agy_match.group(1),
            }
        else:
            return {
                "is_task": False,
                "agy_response": f"เอ่อ... บอสคะ สัญญาณขาดหาย มิน่าประมวลผลคำสั่งไม่ได้เลยค่ะ (Error JSON: {e})\nรบกวนบอสพิมพ์ใหม่อีกรอบได้ไหมคะ? 😅",
            }


def _build_agent_suffix(meta: dict[str, str]) -> str:
    return (
        f"\n\n(Instructions: You are {meta['name']} [Job: {meta['job']}]. "
        f"Personality: {meta['description']}. Respond like a human software developer in character. "
        "Address the user as 'The Boss'. Be extremely brief, conversational, and direct. "
        "Explain in 1-2 short sentences exactly what you did. Do not use AI clichés or preamble. Start directly.\n"
        "CRITICAL MINDSET: 100% Quality & Security Shift-Left. Design before coding. "
        "Write clean, anti-spaghetti SOLID code. Handle edge cases. "
        "Pre-commit is just a typo-catcher; the code MUST be structurally perfect and fully tested "
        "before you finish the task. Zero defects!\n"
        "IMPORTANT: If you need to start a server or long-running process, use run_command with a small WaitMsBeforeAsync so it goes to the background. Do NOT block your execution!\n"
        "ANTI-LOOP PROTOCOL (ค.ว.ย.): If you execute a command and it fails, and a subsequent fix results in the exact same failure, STOP IMMEDIATELY! Do NOT loop blindly. Return a failure report to the Boss explaining the roadblock.\n"
        "APPROVALS: If you need permission for ANYTHING, call the `request_boss_approval` MCP tool "
        "(action, reason, ticket_key). It blocks and returns a final answer — do not poll files, "
        "do not use `schedule`, do not end your turn to wait.)"
    )


async def _dispatch_swarm(
    agent_runner: AgentRunner,
    router_data: dict[str, Any],
    content_str: str,
    message: discord.Message,
) -> None:
    sub_tasks = router_data["sub_tasks"]
    ack_msg = router_data.get(
        "agy_response",
        f"⚡ **Agy [System]:** Whoa, that's a big quest! I'm breaking it down into {len(sub_tasks)} sub-tasks and deploying the Swarm!",
    )

    target_project = router_data.get("target_project")
    project_cwd = None
    if target_project:
        proj_data = ProjectRegistry().get_project(target_project)
        if proj_data:
            project_cwd = proj_data["path"]

    log_activity("agent", "Agy", ack_msg)
    await message.channel.send(ack_msg)
    tasks_to_run = []
    for st in sub_tasks:
        ta = st.get("target_agent", "fullstack-engineer")
        if ta not in AGENTS_METADATA:
            ta = "fullstack-engineer"
        meta = AGENTS_METADATA[ta]
        p = st.get("prompt", content_str)
        sfx = _build_agent_suffix(meta)
        esc_p = p + sfx
        env_vars = (
            {"GITHUB_TOKEN": os.environ.get("GITHUB_MINABOT", "")}
            if os.environ.get("GITHUB_MINABOT")
            else None
        )
        cmd_args = [
            "agy",
            "--dangerously-skip-permissions",
            "--new-project",
            "--print",
            esc_p,
        ]
        tasks_to_run.append(
            agent_runner.run_command_async(
                message.channel,
                message.author.mention,
                p,
                cmd_args,
                meta["name"],
                env_vars=env_vars,
                cwd=project_cwd,
                project_id=target_project or "drunken-team",
            )
        )
    for t in tasks_to_run:
        asyncio.create_task(t)


async def _dispatch_single_agent(
    agent_runner: AgentRunner,
    router_data: dict[str, Any],
    content_str: str,
    message: discord.Message,
) -> None:
    target_agent = router_data.get("target_agent", "fullstack-engineer")
    if target_agent not in AGENTS_METADATA:
        target_agent = "fullstack-engineer"
    agent_meta = AGENTS_METADATA[target_agent]
    refined_prompt = router_data.get("refined_prompt", content_str)

    target_project = router_data.get("target_project")
    project_cwd = None
    if target_project:
        proj_data = ProjectRegistry().get_project(target_project)
        if proj_data:
            project_cwd = proj_data["path"]

    config_file = find_config()
    if config_file:
        active_agent_json = os.path.join(
            os.path.dirname(config_file), "active_agent.json"
        )
        try:
            with open(active_agent_json, "w") as f:
                json.dump({"active_agent": target_agent}, f)
        except Exception:
            pass
    suffix = _build_agent_suffix(agent_meta)
    escaped_prompt = refined_prompt + suffix
    env_vars = (
        {"GITHUB_TOKEN": os.environ.get("GITHUB_MINABOT", "")}
        if os.environ.get("GITHUB_MINABOT")
        else None
    )
    cmd_args = [
        "agy",
        "--dangerously-skip-permissions",
        "--new-project",
        "--print",
        escaped_prompt,
    ]
    asyncio.create_task(
        agent_runner.run_command_async(
            message.channel,
            message.author.mention,
            refined_prompt,
            cmd_args,
            agent_meta["name"],
            env_vars=env_vars,
            cwd=project_cwd,
            project_id=target_project or "drunken-team",
        )
    )


async def _handle_conversational_response(
    router_data: dict[str, Any], direct_response: str, message: discord.Message
) -> None:
    resp = router_data.get("agy_response", direct_response)
    if isinstance(resp, dict):
        resp = str(resp)
    resp = (
        resp.replace('{"is_task": false, "agy_response": "', "")
        .replace('"}', "")
        .strip()
    )
    log_activity("agent", "Agy", resp)
    await message.channel.send(f"⚡ **Agy [System]:** {resp}")


async def _handle_reply_continuation(
    client: discord.Client, agent_runner: AgentRunner, message: discord.Message
) -> bool:
    if not message.reference or not message.reference.message_id:
        return False
    try:
        original_message = await message.channel.fetch_message(
            message.reference.message_id
        )
        if original_message.author != client.user:
            return False

        import re

        # Look for the footer: *Reply to this message to continue working with **{agent_name}** in `{project_id}`*
        match = re.search(r"with \*\*(.*?)\*\* in `([^`]+)`", original_message.content)
        if not match:
            return False

        _ = match.group(1)
        target_project = match.group(2)

        project_info = ProjectRegistry().get_project(target_project)
        _ = project_info.get("path") if project_info else None

        await message.channel.send(
            "⚡ **Agy [System]:** บอสคะ การสนทนาต่อเนื่องผ่าน Discord ถูกปิดใช้งานแล้วค่ะ รบกวนสั่งงานผ่าน Terminal (CLI) แทนนะคะ ⚙️"
        )
        return True
    except Exception as e:
        print(f"Error handling reply: {e}", flush=True)
        return False


class DiscordRouter:
    def __init__(
        self,
        client: discord.Client,
        agent_runner: AgentRunner,
        channel_id: int,
        approval_manager: Any = None,
    ):
        self.client = client
        self.agent_runner = agent_runner
        self.CHANNEL_ID = int(channel_id) if channel_id else 0
        self.approval_manager = approval_manager

    async def route(self, message: discord.Message) -> None:  # noqa: C901
        if message.author == self.client.user:
            return
        print(
            f"[Debug] Received message in channel {message.channel.id} (Configured: {self.CHANNEL_ID}) from {message.author}: {message.content[:50]}",
            flush=True,
        )

        print(
            f"[Debug] Check Channel ID: message {int(message.channel.id)} vs self {self.CHANNEL_ID}",
            flush=True,
        )
        if int(message.channel.id) != self.CHANNEL_ID:
            print("[Debug] Channel ID mismatch! Returning early.", flush=True)
            return

        print("[Debug] Channel ID matches, logging activity...", flush=True)
        log_activity("user", message.author.name, message.content.strip())
        content_str = message.content.strip()
        if not content_str:
            return

        if content_str == "!detail":
            print("[Debug] matched !detail command", flush=True)
            await _handle_detail_command(message)
            return

        print(f"[Debug] processing content_str: {content_str}", flush=True)
        if content_str.startswith("/"):
            await _handle_slash_command(
                self.agent_runner, message, content_str, self.approval_manager
            )
            return

        if await _handle_reply_continuation(self.client, self.agent_runner, message):
            return

        # Free-form task commanding is disabled pending DT-94 -- every
        # non-slash message gets the same answer, regardless of content.
        await message.channel.send(
            "⚡ **Agy [System]:** พิมพ์ `/help` เพื่อดูคำสั่งที่ใช้ได้ตอนนี้ค่ะ "
            "(การสั่งงานอิสระผ่านข้อความยังปิดอยู่ รอ DT-94)"
        )
        return
