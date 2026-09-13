# drunken-guild — instructions for Claude Code

Loaded on every turn, so it holds only what must be true whatever you are touching. Anything that
applies to one half of the tree lives in `.claude/rules/` with `paths:` frontmatter and loads when
you reach a matching file: `ai-layer.md` for skills, agents and templates, `python.md` for `src/`,
`scripts/` and `tests/`.

`SESSION_CHECKPOINT.md` is the other half: **read it at the start of a session.** This file says how
to work; that file says where things stand.

**Another agent working here follows this same file** — no agent-specific plumbing lives in this
repository (DG-349) — with its own name in the commit author and the `agent:` label.

**The repository is being re-scoped to 2.0.0** (Epic DG-348). The target and every decision so far
are in `SESSION_CHECKPOINT.md` §0 — judge any change against it, and do not start work the
inventory has not approved.

---

## What this repo is

**One repository, two deliverables**, and almost every rule follows from that:

| | what it is | where |
|---|---|---|
| **The runtime** | a Python package — the `drunken-jira-mcp` server, the CLI (`drunken-doctor`, `drunken-init`, `drunken-usage`) and the `drunken-hook` permission floor | `src/`, `tests/`, `scripts/` |
| **The AI layer** | the skills and agents that get installed into `~/.claude/` | `skills/`, `agents/`, `templates/`, `examples/` |

It exists because these two were separate repositories that drifted. Skills were authored in four
places with 26 duplicated by name; `git-workflow` silently diverged to 73 lines against 196 while a
just-merged PR told one repo to defer to the other's copy. **One surface is the answer.** Do not
recreate a second one — including by restating a rule in two files.

**The flow is six commands**: `/prd` → `/clarify` → `/ddd` → `/breakdown` → `/build` → `/audit`, one
skill each, in `skills/flow/`. They are the product. **Read the skill rather than reasoning from this
line** — it is a map, not the rule. Anything that does not serve a step of that flow does not belong
in `skills/` (DG-353).

**The AI layer stays in git, deliberately.** DG-250 keeps a project's wrapper directory out of git;
here the AI layer *is* the product, so applying that rule literally would move the deliverable out of
version control. Do not "fix" this repo by moving `skills/` or `agents/` out of git.

*Drunken Programmer* is the pen name; `drunken-guild` is the product. The name says drunk and the
contents are FATAL directives, blast-radius checks and post-mortems. That tension is the brand — do
not soften either half.

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

`pytest -m e2e` talks to **live Jira and files real tickets**. Run it deliberately or not at all. It
is deselected because for months it was not, and it filed 52 junk tickets before anyone noticed.

`drunken-usage --project drunken-guild --by ticket` says what a run cost, read from the host's own
transcripts — nothing is instrumented and nothing is sent anywhere. It knows no prices; rates are an
operator input, and an unpriced model reports no cost rather than a smaller one. The `DG-` key in a
branch name is its only source, so a branch without one reports as untracked cost, silently.

---

## Jira is the source of truth

`TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW**, including for your own work.

**How to write and run a ticket is `skills/workflow/jira-tickets/SKILL.md`** — the
FINDING/SCOPE/ACCEPTANCE shape, the fields this Jira can actually set, and what must be verified
before anything is Done. Read it before opening or closing a ticket. It is the same file every agent
is pointed at, so the rules cannot drift apart per agent.

A ticket is scanned, not read: the story of how you found it belongs in the commit and the PR.

Use the `drunken-jira-mcp` tools, each taking the project id as its first argument. There is no shell
fallback: the bridge script that was one went with the Discord lane (DG-355), because two ways to
write to Jira is two things that can disagree about what happened.

One ticket per phase, and each phase must merge on its own without breaking the one before it.

**A ticket marked IN REVIEW is not merged code.** DG-225 sat in review for weeks while its branch was
never merged and the trunk stayed vulnerable; every surface said it was done. Verify against
`origin/develop` — by looking, with `git merge-base --is-ancestor` — before believing any claim that
something is fixed. A pull request page is a surface too, and it lags (DG-358).

**An action only a person can take at the end goes on the release-gate ticket**, as a comment, in the
session that finds it. A note in a PR body is not read at tag time, and one was acted on in a state
where it broke every Jira tool call.

**There is no local board.** The `board_*` tools are retired and `drunken-board-mcp` is not packaged
(DG-265). Do not create `.claude/board/` or `.agents/board/`, and do not author a skill that reads or
writes one. A board beside Jira is a second surface that can disagree with the first.

**The backlog is not a second status.** `jira_move_to_backlog` and `jira_move_to_board` change
membership of the current working set and nothing else. A ticket parked in the backlog is still
`IN PROGRESS` if that is what it was.

**Assignee is the accountable human; the agent doing the typing is a label.** A ticket an agent is
actively working carries `agent:<name>` in `labels`. Set it; do not repurpose Assignee for it
(DG-293).

---

## Git

**The full rules are one file: `skills/workflow/git-workflow/SKILL.md`.** Branch naming, merge
strategy per target, and the release flow all live there. **Load it rather than reasoning from
memory, and do not restate it here.**

Six things are unrecoverable if you get them wrong, so they are named here as pointers:

- Never push to `main`.
- **An agent opens pull requests; a human merges them.** No exception for your own PR, a one-line
  change, or a green CI.
- Never `git merge` locally against `main` or `develop` and push the result.
- Merge strategy is chosen by target, not preference.
- **An agent commit passes `--author`**, so `git log` tells an agent's commit from the operator's:
  `Claude Code <claude@drunken.local>`, or `<Agent> <agent@drunken.local>` for any other (DG-293).
  The addresses are local-only and resolve nowhere — they exist to be visibly not a real account.
- **Two agents never share a checked-out working tree.** Each works from its own `git worktree`, on
  its own branch (DG-288). One task, one owner, one branch, one worktree, one PR.

Pre-commit runs ruff, ruff-format, mypy and the repository's own guards. Do not bypass it.
**Install it in a fresh clone** — a clone without `.git/hooks/pre-commit` runs no gates at all and
says nothing.

---

## Approvals — ask the person who is reading

Full protocol in `skills/workflow/ask-boss/SKILL.md`; the short version:

- The Boss is reading this conversation → **just ask them here.** That is the whole mechanism now.
- Not reading it → send one notification carrying a link (`core.notify`), park the task, take the
  next unblocked one, and pick the answer up when you next start a session. Asking must never stop
  the rest of the work.
- Nothing is killed for going unanswered, and nothing expires.
- A force push, a hard reset, a recursive delete and reading `.env` are denied by
  `.claude/settings.json` and by the `drunken-hook` floor, **and no answer from anywhere can
  authorise one.** Do not route around it; raise it with the Boss.

**The Boss reporting a problem is evidence that the problem exists.** Do not argue that it does not.
Ask where it happened, which command, and what they saw — then go and look. Every claim you make
carries its evidence or says it has none yet: "I have not measured that" is an answer; a confident
guess is not.

## The deny floor — the layer that answers before the model runs

The **harness** asks before the model runs at all, and the model never sees that one — which is why
no sentence typed in chat has ever been able to redirect it. `drunken-hook` answers there:

1. **On the deny list → denied**, whatever the mode. `bypassPermissions` turns off prompting; it does
   not turn off the floor.
2. **A call carrying no command and no path → denied.** An empty string matches no rule at all, deny
   rules included, so a call nobody can read would otherwise fall past the floor it was meant to hit
   (DG-321).

Everything else gets **silence** — no decision, so the harness prompts exactly as it would have.
Silence is not `allow`: the floor can refuse and it can stand aside, and it never widens permission.

---

## Things that will bite you anywhere

- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal. Show
  `env://…` or `file://…#key`, never a token, channel id, workspace URL or account email inline.
  gitleaks scans full history and `.env` is deliberately not allowlisted.
- **An agent does not delete.** Retired things move to `_not_used/` with a note saying why and what
  replaced them, and *marking a thing unused beats removing it*. **`_not_used/` is not committed**
  (DG-291): the tracked record is `RETIRED.md` at the root, and that row is the only part a fresh
  clone gets — add it in the same change. Anything needing a recursive force-delete becomes a **list
  handed to the Boss to run**. An authorisation recorded in an earlier session is not permission to
  delete today.
- **An agent does not install and does not deploy.** Not the install scripts, not `uv tool install`,
  not a copy into `~/.claude/`. Say what to run and hand it over. Merging is not deploying: the
  installed environment is a separate thing and `drunken-doctor` reports the gap.
- **Do not touch `~/Projects/drunken-team` or `~/Projects/ai-team-toolkit`.** They are the fallback
  until this repo is released and verified.
- **Do not touch another agent's own state** — `~/.gemini/` and anything under it included. Editing a
  file there is an install.
