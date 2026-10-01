# Guild session reminder — SessionStart hook snippet (Claude Code only)

This is a **Claude-only extra**, not part of the portable `templates/CLAUDE.md`. It uses the
`SessionStart` hook in `.claude/settings.json`, a Claude Code mechanism with no equivalent in a
vendor-neutral `AGENTS.md`. **An agent never places or installs a hook** — it does not deploy and
does not install (CLAUDE.md § "Things that will bite you anywhere"). This document hands the
snippet to the Boss; the Boss copies it in.

## Why this extra is still needed (REQ-006 evidence)

The guild roles — manager, worker, reviewer — and the flow commands (`/build`, `/git-workflow`,
`/audit`) live in `AGENTS.md` and the installed skills, and a session that reads them once at the
start already has them. What a long session loses is not the rule but the *habit* of saying which
step it ran — the thing `/audit` checks for after the fact. A `SessionStart` hook re-injects one
line of context at the top of every new session, cheaply and without the agent having to remember
to re-read `AGENTS.md` itself. That is the evidence for keeping a Claude-specific extra beside a
project instructions file that is otherwise vendor-neutral: one does what the other cannot.

## What to do

Add (or merge, if `.claude/settings.json` already has a `hooks` key) this block into the project's
own `.claude/settings.json`, at the project root:

```json
{
  "hooks": {
    "SessionStart": [
      {
        "hooks": [
          {
            "type": "command",
            "command": "printf '%s\\n' '{\"hookSpecificOutput\":{\"hookEventName\":\"SessionStart\",\"additionalContext\":\"Work as the guild: the manager plans and sequences tickets before building starts; the worker builds one approved ticket via /build; the reviewer checks every pull request before the Boss merges. Say which of /build, /git-workflow, jira-tickets, /audit you ran this session.\"}}'"
          }
        ]
      }
    ]
  }
}
```

**Where to place it:** the project root's `.claude/settings.json` — not this repository's. If the
file does not exist yet, create it with just this content; if it exists, merge the `hooks` key in
rather than overwriting whatever else is already there.

## The single-quote warning

The `command` string wraps the reminder in single quotes for the shell (`printf '%s\n' '<json>'`).
**The reminder text must never contain an apostrophe.** One apostrophe closes that quoting early
and the rest reads as a shell syntax error — not a JSON error, so it surfaces as a confusing hook
failure rather than anything that names the cause. If the reminder text ever needs an apostrophe,
rewrite the sentence to avoid it rather than trying to re-escape the command; re-escaping a
single-quoted string that itself sits inside a JSON string, inside a markdown code fence, is a
second source of the same mistake.

## The shell this command needs

`printf` is the only thing this command runs, and it is also the one requirement: whatever shell
`.claude/settings.json` invokes the hook command with on Windows must provide `printf`, and it must
be the shell actually invoked — not merely one that happens to be on `PATH` under the same name.

**One verified fact, from this machine:** running `bash -c "printf …"` from a Python `subprocess`
call resolved to the WSL relay (`C:\Program Files\Git\usr\bin\bash.EXE` on `PATH`, which forwards to
`wsl.exe`) and failed outright — `getpwuid(0) failed`, `execvpe(/bin/bash) failed: No such file or
directory` — because no WSL distribution is registered on this machine. Invoking the absolute path
to Git Bash instead, `C:/Program Files/Git/bin/bash.exe -c "printf …"`, ran the same command and
printed valid JSON on stdout.

**That is not the same thing as a live Claude Code `SessionStart` hook**, which spawns its own
shell rather than a Python `subprocess` call. Whether that shell resolves the same way — Git Bash,
WSL, or something else — is **unverified until the Boss tests it** in an actual session. Say this
to the Boss plainly rather than assuming the one data point above settles it: paste the snippet,
start a new session, and confirm `additionalContext` actually arrives before relying on it.

## Verifying it

1. Confirm the JSON above parses — paste it into any JSON validator, or run
   `python -c "import json,sys; json.load(sys.stdin)"` and paste the block in.
2. Start a new Claude Code session in the project after installing it, then ask which role reviews
   a pull request. The answer should name the **reviewer** role from `AGENTS.md`'s guild block,
   sourced from the injected context rather than guessed.
3. If the hook does not fire or the session reports no additional context, check which shell
   `.claude/settings.json` is invoking on this machine per the note above — a `bash` that resolves
   to an unregistered WSL distribution is the known failure mode.
