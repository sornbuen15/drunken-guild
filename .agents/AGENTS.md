# drunken-guild — instructions for Antigravity

## `CLAUDE.md` is the authority here. Read it first, in full.

`CLAUDE.md` at the repository root is written to Claude Code, but **every rule in it applies to
you**: what this repository is, the commands, Jira, git, tests, authoring the AI layer, what never
to install, approvals, away mode, and the things that will bite you. Where this file and
`CLAUDE.md` disagree, `CLAUDE.md` wins, and the disagreement is a bug in this file.

This file carries only the facts that are genuinely different for you. It used to be a
find-and-replace copy of `CLAUDE.md` — 353 lines each, every rule change made twice — and the
replacement introduced errors of its own: it placed the deny list in a `.gemini/` file the
approval hook never reads (DG-340). A rule written in two places is the failure this repository
exists to cure. **Do not copy a rule from `CLAUDE.md` into this file; point at it.**

`SESSION_CHECKPOINT.md` is the other half: read it at the start of a session. It carries the
current status, including DG-301 — **Antigravity on this repository is supported, not
recommended.** The rules still hold if you run; do not expect work to be assigned to you.

---

## What is different for Antigravity

| | Claude Code | Antigravity |
|---|---|---|
| Commit author (DG-293) | `Claude Code <claude@drunken.local>` | `Antigravity <antigravity@drunken.local>` — pass `--author` on **every** commit, not just the first |
| Ticket label | `agent:claude` | `agent:antigravity` |
| Working tree (DG-288) | the checkout its harness starts in | a separate `git worktree` — `git worktree add ../drunken-guild.antigravity <branch>`, or your runtime's own isolated tree. Never the primary checkout |
| Skills installed to | `~/.claude/skills/` | `~/.gemini/config/skills/` |
| Agents installed to | `~/.claude/agents/` | `~/.gemini/config/skills/`, as a generated variant |
| Global instruction file | — | `~/.gemini/config/AGENTS.md`, from `templates/AGENTS.md` |
| PreToolUse hook config | `.claude/settings.json` → `hooks` | `.agents/hooks.json` |

**The deny list is the same file for both of you: `.claude/settings.json`.** `.agents/hooks.json`
routes your tool calls into the same `drunken-approval-hook`, and that hook reads its allow and
deny rules from `.claude/settings.json` whichever host called it. Force-push, hard reset, `rm -rf`
and touching `.env` are denied to you exactly as they are to Claude, whatever an approval says.

**`.git/hooks/pre-commit` must be installed** in whatever checkout you commit from. The
worktree-isolation check identifies your commits by the `--author` above; a commit made without it
is invisible to that check, and a checkout without the hook runs no gate at all.

**Do not touch `~/.gemini/antigravity-cli/brain/*/worktrees/` belonging to another session, and do
not edit anything under `~/.gemini/` as part of a change here** — editing a file there is an
install, and installing is the Boss's step (`CLAUDE.md`, "Installing is the operator's job").
