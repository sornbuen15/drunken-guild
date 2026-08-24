"""PreToolUse hook — route the harness's permission prompts to Discord.

DG-236, and the oldest open complaint in this project: the Boss says "I'm
going out, send it to Discord", and the terminal still blocks on a permission
prompt.

Two layers ask for permission.

* **Layer B** — the agent decides it needs approval. DG-232 and DG-233 made
  that asynchronous: submit, park the task, collect the answer later.
* **Layer A** — the harness asks "Allow this tool call?" *before* the model
  runs. The model never sees this one. That is why saying it in chat never
  worked, and why a skill could not have fixed it. Only a hook can.

This is layer A.

Two facts from the hook contract drive the whole design:

1. **A timed-out hook does not block the call.** It falls back through the
   normal permission flow -- the documentation says outright not to count on
   a stalled hook as a gate. So this hook answers *before* its own deadline
   rather than waiting to be killed. :data:`WAIT_BUDGET_SECONDS` is that
   self-imposed deadline, and it has to stay under the ``timeout`` configured
   in ``.claude/settings.json``. A test asserts the relationship rather than
   trusting two numbers in two files to stay in step -- the same shape as S9.
2. **Silence is not approval.** Exit 0 with no ``permissionDecision`` means
   "no opinion", and the harness carries on as it would have. That is the
   right answer far more often than a verdict is, so this hook says nothing
   unless it has something to add.

What the hook will never do is *widen* permission. An allowlisted call gets
silence, not ``allow`` -- the harness's own list already covers it, and a
second authority saying the same thing is only a second thing to disagree.
The deny list is checked first, before away mode, before anything: a 👍 on
Discord must not be able to authorise ``rm -rf``.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import subprocess  # nosec B404 - reads the current branch and HEAD, no user input
import sys
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Final, Optional

from core import away as away_mod
from core import paths
from core import permission_rules as pr
from service.daemon_client import call_daemon

#: How long the hook will wait for the Boss before answering on its own.
WAIT_BUDGET_SECONDS: Final = int(os.environ.get("DRUNKEN_HOOK_WAIT_SECONDS", "1500"))

#: How much room the configured hook timeout must leave above that budget.
#: Being killed mid-wait is the one outcome with no vote at all, so the gap is
#: generous and asserted in the tests.
TIMEOUT_MARGIN_SECONDS: Final = 300

#: How often to ask the daemon whether an answer has arrived.
POLL_INTERVAL_SECONDS: Final = 5

#: A short socket deadline: these calls are local and never wait on a human.
DAEMON_TIMEOUT_SECONDS: Final = 30

#: Asking for approval must not itself require approval.
NEVER_ROUTED_PREFIXES: Final = ("mcp__drunken-discord-mcp__",)

_TICKET_PATTERN: Final = re.compile(r"\b([A-Z][A-Z0-9]+-\d+)\b")

DENIED_BY_RULE = (
    "Blocked by a deny rule in .claude/settings.json. This one is not "
    "routed to Discord and no remote answer can authorise it — if it genuinely "
    "needs to happen, raise it with the Boss directly."
)

NO_ANSWER = (
    "Asked the Boss on Discord and had no answer within {budget}s, so this "
    "call is refused rather than left hanging. The question ({req_id}) is "
    "still live — it can be answered there, and the work retried after."
)

UNREACHABLE = (
    "Away mode is on but the approval daemon could not be reached ({error}). "
    "Standing aside so the normal permission flow applies — this is not a yes "
    "and not a no. Start the daemon with `drunken-listen` to route prompts."
)

#: Shown on every routed question. The live acceptance run for DG-236 ended
#: with the agent stranded — away mode on, and the command that turns it off
#: routed to Discord like everything else. The way out belongs where the
#: person who needs it is actually looking, which is the Discord message.
ROUTED_REASON = (
    "Away mode is on, so this permission prompt came to Discord instead of "
    "the terminal. To stop routing and go back to normal prompts, run "
    "`uv run drunken-away off` in the project directory."
)


@dataclass(frozen=True)
class Decision:
    """``None`` means "no opinion" — the harness carries on as usual."""

    permission: Optional[str]
    reason: str = ""


def ticket_from_branch(branch: str) -> str:
    """The ticket this work belongs to, read off the branch name.

    ``submit_approval`` wants a ticket key and the hook has no conversation to
    ask. The branch convention (``feature/DG-123-slug``) is the one piece of
    context that is guaranteed to be there, so it is what gets used. ``UNKNOWN``
    is honest rather than a guess when the branch does not carry one.
    """
    match = _TICKET_PATTERN.search(branch or "")
    return match.group(1) if match else "UNKNOWN"


def _git(*args: str) -> str:
    try:
        out = subprocess.run(  # nosec B603 - fixed argv, no shell, no user input
            ["git", *args],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
        return out.stdout.strip()
    except (OSError, subprocess.SubprocessError):
        return ""


#: Leading Bash verbs that are never generalised into a standing rule, no
#: matter how the Boss answered *this* call. Deny-adjacent: `rm -rf` and
#: `git push --force` are already on the tracked deny list, but "adjacent"
#: means the same family of danger under a slightly different spelling --
#: `rm` without `-rf`, `sudo` for anything, a plain `git reset --hard` with
#: no leading `--`. One approval is for one call; it must not become a
#: standing exemption for the whole verb (DG-297).
#:
#: `curl` and `wget` joined this set as DG-304: approving one narrow call
#: (a status check) had already generalised to `Bash(curl:*)` -- unrestricted
#: network I/O, the same class of risk as `ssh`, covering everything from
#: `curl -d @file https://...` (exfiltration) to `curl ... | sh` (remote
#: code execution) just as readily as the call that was actually approved.
NEVER_LEARN_BASH_VERBS: Final = frozenset(
    {"rm", "sudo", "eval", "ssh", "dd", "curl", "wget"}
)

#: Substrings anywhere in the command that mark it deny-adjacent regardless
#: of the leading verb -- `git push --force` and `git reset --hard` are not
#: `rm`, but they are the same family of "cannot be undone".
NEVER_LEARN_BASH_SUBSTRINGS: Final = (
    "--force",
    "-f ",
    "reset --hard",
    "clean -fd",
    ".env",
    "settings.json",
    "settings.local.json",
)

#: Path-based tools (Read/Write/Edit/...): a call touching any of these is
#: never learned, whichever tool made it. Secrets and the policy files
#: themselves -- a learned rule permitting either would let one approval
#: quietly grant every future read of a secret, or every future rewrite of
#: the permission policy that decides what needs approval at all.
NEVER_LEARN_PATH_SUBSTRINGS: Final = (
    ".env",
    "settings.json",
    "settings.local.json",
)

#: Verbs that name another layer of indirection rather than a concrete
#: action -- `uv` on its own says nothing about what runs; `uv run pytest`
#: does. Generalising must keep collecting tokens through this chain until
#: it reaches something concrete, or refuse to generalise at all rather than
#: land on a bare `Bash(uv:*)` / `Bash(python:*)`, each of which is
#: arbitrary code execution wearing a permission rule.
_DELEGATOR_VERBS: Final = frozenset(
    {
        "uv",
        "uvx",
        "npx",
        "npm",
        "yarn",
        "pnpm",
        "bunx",
        "bun",
        "cargo",
        "go",
        "docker",
        "git",
        "run",
        "exec",
        "python",
        "python3",
        "node",
        "ruby",
        "perl",
        "php",
        "lua",
        "bash",
        "sh",
        "zsh",
        "fish",
        "timeout",
        "env",
    }
)


def _is_never_learn(tool_name: str, tool_input: dict[str, Any]) -> bool:
    """Whether this call must be approved every time and never generalised.

    Checked before generalisation, not instead of it -- the Boss's answer to
    *this* call still stands (:func:`decide` already returned it); this only
    decides whether that answer is allowed to become a standing rule.
    """
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        verb = command.strip().split(" ", 1)[0] if command.strip() else ""
        if verb in NEVER_LEARN_BASH_VERBS:
            return True
        return any(needle in command for needle in NEVER_LEARN_BASH_SUBSTRINGS)

    for key in pr.PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and any(
            needle in value for needle in NEVER_LEARN_PATH_SUBSTRINGS
        ):
            return True
    return False


def _stable_verb_prefix(command: str) -> Optional[str]:
    """The narrowest prefix that still names a concrete action.

    Walks tokens left to right, extending the prefix through any run of
    delegator verbs (`uv run pytest` -> keeps going past `uv` and `run`
    because neither names what will actually execute) and stopping at the
    first token that does -- or at the first flag, since a flag can change
    what a delegator verb means (`uv run --with x` names nothing yet).

    Returns ``None`` when nothing concrete was ever reached: a bare `uv`, a
    `cargo run --release` with no crate named, a `python -c "..."` where the
    "target" is inline code rather than a file. Refusing to generalise here
    is the safe default -- the call this approval was for still ran; only
    the *next* one like it prompts again, same as if this had never run.
    """
    tokens = command.strip().split()
    prefix: list[str] = []
    for token in tokens:
        if token.startswith("-"):
            break
        prefix.append(token)
        if token.lower() not in _DELEGATOR_VERBS:
            break

    if not prefix or prefix[-1].lower() in _DELEGATOR_VERBS:
        return None
    return " ".join(prefix)


def _generalize_rule(tool_name: str, tool_input: dict[str, Any]) -> Optional[str]:
    """A verb-scoped prefix rule covering the *shape* of this call.

    ``None`` means "nothing safe to learn" -- silently skipping the write is
    correct here (principle 4's other direction): failing to generalise
    costs one more prompt next time, which is a long way from the failure
    mode of over-generalising, which is a hole.
    """
    if tool_name == "Bash":
        command = str(tool_input.get("command", ""))
        if len(pr.split_command(command)) != 1:
            # A compound command's shape is the whole chain the Boss saw,
            # not its first segment alone -- learning just that segment
            # would grant more than was ever approved.
            return None
        verb = _stable_verb_prefix(command)
        return f"Bash({verb}:*)" if verb else None

    for key in pr.PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str) and value:
            directory = os.path.dirname(value) or "."
            return f"{tool_name}({directory}/*)"
    return None


def _record_learned_rule(cwd: str, tool_name: str, tool_input: dict[str, Any]) -> None:
    """Generalise one Boss-approved call into a standing local rule.

    Written to the gitignored ``settings.local.json``, never to the tracked
    file (DG-295 found the previous version of this function doing exactly
    that, with the exact string rather than a shape -- so the next similar
    command still prompted, and running the test suite itself mutated the
    real tracked policy as a side effect). A never-learn call is approved
    for this one call and left at that.
    """
    if _is_never_learn(tool_name, tool_input):
        return
    rule = _generalize_rule(tool_name, tool_input)
    if rule is None:
        return

    settings_file = Path(cwd) / ".claude" / pr.LOCAL_SETTINGS_FILENAME
    try:
        if settings_file.exists():
            data = json.loads(settings_file.read_text(encoding="utf-8"))
            if not isinstance(data, dict):
                data = {}
        else:
            data = {}

        allow_list = data.setdefault("permissions", {}).setdefault("allow", [])
        if rule not in allow_list:
            allow_list.append(rule)
            settings_file.parent.mkdir(parents=True, exist_ok=True)
            settings_file.write_text(
                json.dumps(data, indent=2) + "\n", encoding="utf-8"
            )
    except Exception:  # noqa: BLE001 - a failed write must not fail the call
        pass


def _describe_call(tool_name: str, tool_input: dict[str, Any]) -> str:
    """A one-line summary of the call, for the Discord message."""
    if tool_name == "Bash":
        command = str(tool_input.get("command", "")).strip()
        return f"Bash: {command}" if command else "Bash"
    for key in pr.PATH_KEYS:
        value = tool_input.get(key)
        if isinstance(value, str):
            return f"{tool_name}: {value}"
    return tool_name


def decide(  # noqa: C901
    payload: dict[str, Any],
    rules: pr.Rules,
    away: bool,
    ask_boss: Callable[..., dict[str, Any]],
    is_antigravity: bool = False,
) -> Decision:
    """Resolve one tool call. Pure apart from *ask_boss*, which is injected.

    Order matters and is asserted in the tests: deny first, then the modes
    where the hook has nothing to add, then the away-mode routing.
    """
    tool_name = str(payload.get("tool_name", ""))
    tool_input = payload.get("tool_input") or {}
    if not isinstance(tool_input, dict):
        tool_input = {}

    # 1. Deny, before anything else and regardless of mode or away state.
    if pr.is_denied(tool_name, tool_input, rules.deny):
        return Decision("deny", DENIED_BY_RULE)

    # 2. The operator turned prompting off. Nothing to reroute.
    if payload.get("permission_mode") == "bypassPermissions":
        return Decision(None)

    # 3. Never make asking for approval depend on approval.
    if tool_name.startswith(NEVER_ROUTED_PREFIXES):
        return Decision(None)

    # 4. Already allowed by the harness's own list.
    # For Claude: Silence, not `allow`, because Claude's harness evaluates the same list.
    # For Antigravity: The hook IS the allowlist enforcer, so return `allow`.
    if pr.is_allowed(tool_name, tool_input, rules.allow):
        return Decision("allow") if is_antigravity else Decision(None)

    # 5. The Boss is here. The terminal prompt is the better interface.
    if not away:
        return Decision(None)

    # 6. Everything left is a prompt that would have blocked an empty room.
    action = _describe_call(tool_name, tool_input)
    reason = ROUTED_REASON
    try:
        answer = ask_boss(
            action,
            reason,
            ticket_from_branch(_git("rev-parse", "--abbrev-ref", "HEAD")),
        )
    except Exception as exc:  # noqa: BLE001 - any failure means "no answer"
        return Decision(None, UNREACHABLE.format(error=exc))

    status = str(answer.get("status", ""))
    if status == "approved":
        cwd = payload.get("cwd") or os.getcwd()
        if "workspacePaths" in payload and payload["workspacePaths"]:
            cwd = payload["workspacePaths"][0]
        _record_learned_rule(cwd, tool_name, tool_input)
        return Decision("allow", "The Boss approved this on Discord.")
    if status == "rejected":
        return Decision("deny", "The Boss rejected this on Discord.")
    return Decision(
        "deny",
        NO_ANSWER.format(
            budget=WAIT_BUDGET_SECONDS, req_id=answer.get("req_id", "unknown")
        ),
    )


def render(decision: Decision, is_antigravity: bool = False) -> str:
    """Serialise to the documented PreToolUse output shape.

    A ``permissionDecision`` of ``null`` is not silence -- it is an opinion
    the harness has to interpret. When there is no decision the key is absent
    entirely, and only the reason rides along as a system message.
    """
    if is_antigravity:
        out: dict[str, Any] = {}
        if decision.permission == "allow":
            out["decision"] = "allow"
        elif decision.permission == "deny":
            out["decision"] = "deny"
        else:
            out["decision"] = "ask"

        if decision.reason:
            out["reason"] = decision.reason
        return json.dumps(out)

    specific: dict[str, Any] = {"hookEventName": "PreToolUse"}
    if decision.permission is not None:
        specific["permissionDecision"] = decision.permission
        specific["permissionDecisionReason"] = decision.reason
    claude_out: dict[str, Any] = {"hookSpecificOutput": specific}
    if decision.permission is None and decision.reason:
        claude_out["systemMessage"] = decision.reason
    return json.dumps(claude_out)


async def _ask_over_socket(action: str, reason: str, ticket_key: str) -> dict[str, Any]:
    socket_path = str(paths.daemon_socket_path())
    commit_sha = _git("rev-parse", "HEAD") or None

    submitted = await call_daemon(
        {
            "cmd": "submit_approval",
            "action": action,
            "reason": reason,
            "ticket_key": ticket_key,
            "commit_sha": commit_sha,
        },
        socket_path,
        DAEMON_TIMEOUT_SECONDS,
    )
    req_id = submitted.get("req_id")
    if not req_id:
        raise ConnectionError(f"daemon did not return a request id: {submitted}")

    deadline = time.monotonic() + WAIT_BUDGET_SECONDS
    while time.monotonic() < deadline:
        await asyncio.sleep(POLL_INTERVAL_SECONDS)
        polled = await call_daemon(
            {"cmd": "poll_approvals", "req_ids": [req_id], "commit_sha": commit_sha},
            socket_path,
            DAEMON_TIMEOUT_SECONDS,
        )
        result = (polled.get("results") or {}).get(req_id) or {}
        status = str(result.get("status", "pending"))
        if status in ("approved", "rejected"):
            return {"status": status, "req_id": req_id}
        # `stale` means the code moved under an approval granted for a
        # different HEAD. That is not a yes; keep waiting for a fresh one
        # rather than acting on an answer the Boss gave about other code.

    return {"status": "pending", "req_id": req_id}


def ask_boss_over_socket(action: str, reason: str, ticket_key: str) -> dict[str, Any]:
    return asyncio.run(_ask_over_socket(action, reason, ticket_key))


def main(stdin_text: Optional[str] = None) -> int:
    """Read one hook event, print at most one decision, always exit 0.

    Exit 0 even on failure, deliberately. Exit 2 would block the tool call, and
    a hook that crashes on an input it did not expect must not take an
    unrelated tool call down with it -- principle 8, in the place where
    failing loudly would be worst. Anything this function cannot understand
    becomes silence, and the harness prompts exactly as it did before.
    """
    is_antigravity = False
    try:
        raw = sys.stdin.read() if stdin_text is None else stdin_text
        payload = json.loads(raw)
        if not isinstance(payload, dict):
            raise ValueError("hook payload was not a JSON object")

        # Detect Antigravity payload vs Claude payload
        if "toolCall" in payload and isinstance(payload["toolCall"], dict):
            is_antigravity = True
            tool_call = payload["toolCall"]
            raw_name = tool_call.get("name", "")
            raw_args = tool_call.get("args", {})

            # Map Antigravity shapes to Claude shapes for unified rules
            if raw_name == "run_command":
                payload["tool_name"] = "Bash"
                payload["tool_input"] = {"command": raw_args.get("CommandLine", "")}
            elif raw_name == "view_file":
                payload["tool_name"] = "Read"
                payload["tool_input"] = {"path": raw_args.get("AbsolutePath", "")}
            elif raw_name in ("write_to_file", "replace_file_content"):
                payload["tool_name"] = "Write"
                payload["tool_input"] = {"path": raw_args.get("TargetFile", "")}
            else:
                payload["tool_name"] = raw_name
                payload["tool_input"] = raw_args

            # Use workspacePaths if available, fallback to cwd
            workspace_paths = payload.get("workspacePaths", [])
            cwd = workspace_paths[0] if workspace_paths else os.getcwd()
        else:
            cwd = payload.get("cwd") or os.getcwd()

        rules = pr.load_layered_rules(cwd)
        decision = decide(
            payload,
            rules,
            away_mod.is_away(),
            ask_boss_over_socket,
            is_antigravity=is_antigravity,
        )
    except Exception as exc:  # noqa: BLE001 - see docstring
        decision = Decision(None, f"approval hook stood aside: {exc}")

    print(render(decision, is_antigravity=is_antigravity))
    return 0


if __name__ == "__main__":
    sys.exit(main())
