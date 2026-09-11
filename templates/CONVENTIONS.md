# Aider conventions — <Your Project Name>

> **This is a template.** Copy it to your project root as `CONVENTIONS.md`, beside
> `.aider.conf.yml`, which loads it and `CLAUDE.md` into every Aider session read-only. Authored in
> `drunken-guild`'s `templates/CONVENTIONS.md`; a project's own copy is its own to change.
>
> Deliberately thin. The rules live in **one** file, the project's `CLAUDE.md`. This one carries
> only what is different about Aider, because a rulebook per tool is a rulebook per tool that
> drifts.

---

## `CLAUDE.md` is the authority here

It is written to Claude Code, but **every rule in it applies to you**: the Jira lifecycle, the
approval protocol, git, what must never be deleted, the build and test commands, and where the
project's documents are. Where this file and `CLAUDE.md` disagree, `CLAUDE.md` wins.

## What is different for Aider

- **Aider does not commit here.** `.aider.conf.yml` turns off `auto-commits` and `dirty-commits`.
  Aider's own commit messages follow neither the project's commit format nor its review rule, and
  a commit nobody described is exactly what the git rules in `CLAUDE.md` exist to prevent. Stop
  when the change is ready and let the human commit and open the pull request.
- **No MCP.** Aider cannot call `drunken-jira-mcp`. Name the ticket you are working on in the
  conversation; the human moves it in Jira. Do not keep a ticket list in a file instead — Jira is
  the only coordination surface.
- **Approvals.** Anything `CLAUDE.md` says needs the Boss's approval, ask for in the conversation
  and stop. Aider has no asynchronous channel.
