# AGENTS.md — drunken-guild

<!-- guild-block:start -->
## The guild block — what to pick up, where, when

Pointers only — read the skill, role or tool named; do not reason from this table alone.

| situation | pick up |
|---|---|
| **new project** | `/prd` → `/clarify` → `/ddd` → `/breakdown` in that order, then `/replan` once a requirement changes after the backlog already exists. |
| **an approved task ready to build** | `/build` via the **worker** role. |
| **a plan, tests, or proposed change to review** | the **reviewer** role. |
| **planning or breaking work into tasks** | the **manager** role. |
| **git — branch, commit, PR, merge strategy** | `/git-workflow` (`skills/workflow/git-workflow/SKILL.md`). |
| **a Jira issue — write, read, or move it** | Optional: `/jira-tickets` plus registered `jira_*` MCP tools. |
| **start, hand off or close a work session** | `/session-checkpoint` — read the local handoff note at start; update it before handing off. |
| **end of day / verify what shipped** | `/audit`. |
| **something destructive, irreversible or merge-worthy needs the Boss's approval** | `/ask-boss` (`skills/workflow/ask-boss/SKILL.md`). |
| **unsure which skill, role or tool fits** | `skills/INDEX.md` — read it rather than guessing a name from memory. |
<!-- guild-block:end -->

Shared instruction entry point. Agent discovery differs; see `docs/AGENT-COMPATIBILITY.md` for
per-agent evidence.
**Amended** (REQ-006, Q3-A): a generated one-line adapter that only points at this standard is
allowed — a project's own `CLAUDE.md` is exactly that when it carries nothing beyond `@AGENTS.md`.

`SESSION_CHECKPOINT.md` is optional local handoff state: use `/session-checkpoint` to read it at
session start and update it when persistent notes will help another session. The real file is
ignored by Git; only `templates/SESSION_CHECKPOINT.md`, its blank seed, is tracked.
`.ai/PRD.md` and `.ai/DOMAIN.md` hold accepted requirements and vocabulary.

---

## What this repo is

**One repository, two deliverables**: the Python runtime and optional integrations are in `src/`,
`tests/`, `scripts/`; portable skills and roles are in `skills/`, `agents/`, `templates/`, `examples/`.

The flow is `/prd` → `/clarify` → `/ddd` → `/breakdown` → `/build` → `/audit`, with `/replan` when
requirements change. Start at the step that fits the task and read its skill.

---

## Commands

```bash
uv sync --extra dev                 # required, not optional
uv run pytest -q                    # e2e is deselected by default, on purpose
uv run ruff check src/ tests/ scripts/
uv run ruff format src/ tests/
uv run mypy src                     # --strict via pyproject
uvx bandit -ll -q -r src/           # with pip-audit --strict, also gates CI
./scripts/verify_clean_install.sh   # clean-room checks, touches nothing of yours
```

`drunken-usage` estimates usage from supported local transcripts — nothing is instrumented and nothing is sent anywhere;
rates are operator-provided, and an unpriced model reports no cost rather than a smaller one. See its documentation for limits.

A pull request page is a surface too, and it lags the actual Git revision; verify the revision itself.

**Checks follow acceptance criteria.** For a regression test, run it before the fix when practical;
otherwise say that it was not observed failing. Report actual check output, not claims.

---

Work tracking is optional. Use user requests or project files as task context; use Jira only when
registered and selected. Its absence must not block the SDLC flow. When selected, consult
`skills/workflow/jira-tickets/SKILL.md` for its tool contract.

**Instruction files are not disposable.** A project's `AGENTS.md`, `CLAUDE.md`, and other agent
configuration may be essential even when the project does not use Drunken Guild. Never delete,
untrack, overwrite, or add ignore rules for them just because they are AI-layer files or mention a
different workflow. Change them only when the project owner explicitly asks. Guild migration means
removing files from Git tracking while preserving them on disk, with backup and review; it is an
explicit migration, never an automatic cleanup.

---

## Git

**The full rules are one file: `skills/workflow/git-workflow/SKILL.md`.** Load it before Git actions.

Six things are unrecoverable if you get them wrong, so they are named here as pointers:

- **This repository's protected delivery target is `develop`; `main` is out of scope.** Never
  push, open a pull request targeting, or merge into `main`. A human reviews and decides whether
  to merge approved work into `develop`; agents do not merge.
- Do not commit, push, or open a pull request unless the user or repository workflow authorizes it.
- **When commits are authorized, an agent commit passes `--author`**, so `git log` tells an agent's commit from the operator's:
  `Claude Code <claude@drunken.local>`, or `<Agent> <agent@drunken.local>` for any other (DG-293) —
  local-only addresses that resolve nowhere, to be visibly not a real account.
- **Concurrent agents do not share a mutable working tree.** Each works from its own `git worktree`,
  on its own branch (DG-288). One task, one owner, one branch, one worktree, one PR.

Pre-commit runs ruff, ruff-format, mypy and the repository's own guards; do not bypass it, and
**install it in a fresh clone** — one without `.git/hooks/pre-commit` runs no gates and says
nothing.

---

## Approvals — ask the person who is reading

Full protocol in `skills/workflow/ask-boss/SKILL.md`; the short version:

- The Boss is reading this conversation → **just ask them here.** That is the whole mechanism now.
- Not reading it → send one notification carrying a link (`core.notify`), park the task, take the
  next unblocked one, and pick the answer up next session. Nothing is killed for going unanswered.
- A force push, a hard reset, a recursive delete and reading `.env` are denied by
  `.claude/settings.json` and by the `drunken-hook` floor, **and no answer from anywhere can
  authorise one.** Do not route around it; raise it with the Boss.

**The Boss reporting a problem is evidence that the problem exists.** Ask where it happened, which
command, and what they saw — then go and look. Every claim carries its evidence or says it has
none yet: "I have not measured that" is an answer; a confident guess is not.

## The deny floor — the layer that answers before the model runs

The **harness** asks before the model runs at all, and the model never sees that one — which is
why no sentence typed in chat has ever been able to redirect it. `drunken-hook` answers there:

1. **On the deny list → denied**, whatever the mode — `bypassPermissions` turns off prompting; it
   does not turn off the floor.
2. **A call carrying no command and no path → denied**, so a call nobody can read cannot fall past
   the floor it was meant to hit (DG-321).
3. **A call that would skip or disable the git hooks → denied** (DG-465): `--no-verify`/`git commit -n`, `core.hooksPath`, `SKIP=`/`DRUNKEN_NO_REGISTERED_PROJECTS=` on a git command, `pre-commit uninstall`, or `rm`/`mv`/`chmod`/`Write`/`Edit` on `.git/hooks` — hardcoded here, since a settings rule can't see a flag mid-command.

Everything else gets **silence** — no decision, so the harness prompts exactly as it would have.
Silence is not `allow`: the floor can refuse and it can stand aside, and it never widens
permission.

---

## Things that will bite you anywhere

- **English only** — every description, instruction, commit, comment and PR this repository sees.
- **No registered id in a commit** (REQ-023): fixtures, examples, messages use alpha, beta, zeta.
- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal: show
  `env://…` or `file://…#key`, never a token, channel id, workspace URL or account email inline.
  gitleaks scans full history and `.env` is deliberately not allowlisted.
- **An agent does not delete.** Retired things move to `_not_used/` (not committed, DG-291) with a
  note saying why and what replaced them; the tracked record is `RETIRED.md` at the root, added in
  the same change. A recursive force-delete becomes a **list handed to the Boss to run** — an
  authorisation recorded in an earlier session is not permission to delete today.
- **An agent does not install and does not deploy** — not the install scripts, not
  `uv tool install`, not a copy into an agent's own config directory. Say what to run and hand it
  over; merging is not deploying, and `drunken-doctor` reports the gap.
- **Do not touch `~/Projects/drunken-team` or `~/Projects/ai-team-toolkit`** (the fallback until
  this repo is released) **or another agent's own state**, `~/.gemini/` included: editing it is an install.

---

## Editing this repository's own code and skills — Claude-only detail, same essentials for anyone

`.claude/rules/` carries the full authoring detail for whoever is editing `skills/`, `agents/` or
`src/` here — `ai-layer.md` for the AI layer, `python.md` for the Python half — and loads
automatically for Claude Code via `paths:` frontmatter, staying a Claude-only extra (REQ-006,
Q9-A). Another agent working here still needs the essentials: a skill is
`skills/<category>/<name>/SKILL.md`, an agent is `agents/<name>.md`, both opening with YAML
frontmatter and a `<system_prompt>` block, and **`description` is the only activation trigger** —
nothing matches keywords. `uv sync --extra dev` first, always, in a fresh clone. The Python gates
(`ruff`, `mypy`, `pytest`, `bandit`, `pip-audit`) cover `src/`, `tests/` and `scripts/` only;
`scripts/check_doc_drift.py` and review guard the AI layer, since markdown has no type checker.
