# AGENTS.md — drunken-guild

<!-- guild-block:start -->
## The guild block — what to pick up, where, when

Pointers only — read the skill, role or tool named; do not reason from this table alone.

| situation | pick up |
|---|---|
| **new project** | `/prd` → `/clarify` → `/ddd` → `/breakdown` in that order, then `/replan` once a requirement changes after the backlog already exists. |
| **a ticket ready to build** | `/build`, run by the **worker** role, its pull request read by the **reviewer** role before a human merges it. |
| **planning or breaking work into tickets** | the **manager** role. |
| **git — branch, commit, PR, merge strategy** | `/git-workflow` (`skills/workflow/git-workflow/SKILL.md`). |
| **a Jira ticket — write it, read it, move it** | `/jira-tickets` (`skills/workflow/jira-tickets/SKILL.md`) plus the `jira_*` MCP tools. |
| **end of day / closing a session** | `/audit`. |
| **something destructive, irreversible or merge-worthy needs the Boss's approval** | `/ask-boss` (`skills/workflow/ask-boss/SKILL.md`). |
| **unsure which skill, role or tool fits** | `skills/INDEX.md` — read it rather than guessing a name from memory. |
<!-- guild-block:end -->

Loaded by every agent working in this repository — Claude Code, Antigravity, Aider, Gemini CLI,
whichever is in the seat. No agent-specific plumbing lives here (DG-349): the same file, the same
rules, whoever is typing — with that agent's own name in the commit author and the `agent:` label.
**Amended** (REQ-006, Q3-A): a generated one-line adapter that only points at this standard is
allowed — a project's own `CLAUDE.md` is exactly that when it carries nothing beyond `@AGENTS.md`.

`SESSION_CHECKPOINT.md` is the other half: **read it at the start of a session.** This file says
how to work; that file says where things stand.

**The repository is being re-scoped to 2.0.0** (Epic DG-348). The target and every decision so far
are in `.ai/PRD.md`, and its vocabulary in `.ai/DOMAIN.md` — judge any change against them, and do
not start work the inventory has not approved.

---

## What this repo is

**One repository, two deliverables**, and almost every rule follows from that: **the runtime** —
a Python package, the `drunken-jira-mcp` server, the CLI (`drunken-doctor`, `drunken-init`,
`drunken-usage`) and the `drunken-hook` permission floor, in `src/`, `tests/`, `scripts/` — and
**the AI layer** — the skills and agents installed into each agent's own location, in `skills/`,
`agents/`, `templates/`, `examples/`.

It exists because these two were separate repositories that drifted — skills authored in four
places with 26 duplicated by name, `git-workflow` silently diverged to 73 lines against 196. **One
surface is the answer.** Do not recreate a second one — including by restating a rule in two files.

**The flow is seven commands** — `/prd` → `/clarify` → `/ddd` → `/breakdown` → `/build` → `/audit`,
plus `/replan` when a requirement moves after the backlog exists — one skill each in `skills/flow/`
(README maps them). **Read the skill rather than reasoning from this line.** Anything that does not
serve a step of that flow does not belong in `skills/` (DG-353, amended by DG-386).

**The AI layer stays in git, deliberately** (DG-250): here it *is* the product, so do not "fix"
this repo by moving `skills/` or `agents/` out of version control. *Drunken Programmer* is the pen
name; `drunken-guild` is the product — the tension between the name and FATAL directives is the
brand.

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

`pytest -m e2e` talks to **live Jira and files real tickets**. Run it deliberately or not at all —
it is deselected because for months it was not, and it filed 52 junk tickets before anyone noticed.

`drunken-usage --project drunken-guild --by ticket` says what a run cost, read from the host's own
transcripts — nothing is instrumented and nothing is sent anywhere. It knows no prices; rates are
an operator input, and an unpriced model reports no cost rather than a smaller one. The `DG-` key
in a branch name is its only source, so a branch without one reports as untracked cost, silently.

**A test for a bug or a security finding is seen failing first.** A test written after the fix
proves only that it compiles — say so in the PR, and quote the failure's test id and assertion.

---

## Jira is the source of truth

`TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW**, including for your own
work.

**How to write and run a ticket is `skills/workflow/jira-tickets/SKILL.md`** — the
FINDING/SCOPE/ACCEPTANCE shape, the fields this Jira can actually set, and what must be verified
before anything is Done. Read it before opening or closing a ticket; it is the same file every
agent is pointed at. Use the `drunken-jira-mcp` tools, each taking the project id as its first
argument — there is no shell fallback (DG-355).

**A ticket marked IN REVIEW is not merged code.** DG-225 sat in review for weeks while its branch
was never merged and the trunk stayed vulnerable; every surface said it was done. Verify against
`origin/develop` — by looking, with `git merge-base --is-ancestor` — before believing any claim
that something is fixed. A pull request page is a surface too, and it lags (DG-358).

**An action only a person can take at the end goes on the release-gate ticket**, as a comment, in
the session that finds it — a note in a PR body is not read at tag time.

**There is no local board** (DG-265): do not create or author a skill that reads or writes
`.claude/board/` or `.agents/board/` — a board beside Jira is a second surface that can disagree
with the first. **The backlog is not a second status**: `jira_move_to_backlog` and
`jira_move_to_board` change membership of the current working set, nothing else.

**Assignee is the accountable human; the agent doing the typing is a label.** A ticket an agent is
actively working carries `agent:<name>` in `labels` — set it; do not repurpose Assignee for it
(DG-293).

---

## Git

**The full rules are one file: `skills/workflow/git-workflow/SKILL.md`.** Branch naming, merge
strategy per target, and the release flow all live there. **Load it rather than reasoning from
memory, and do not restate it here.**

Six things are unrecoverable if you get them wrong, so they are named here as pointers:

- Never push to `main`, and never `git merge` locally against `main` or `develop` and push the
  result. Merge strategy is chosen by target, not preference.
- **An agent opens pull requests; a human merges them.** No exception for your own PR, a one-line
  change, or a green CI.
- **An agent commit passes `--author`**, so `git log` tells an agent's commit from the operator's:
  `Claude Code <claude@drunken.local>`, or `<Agent> <agent@drunken.local>` for any other (DG-293) —
  local-only addresses that resolve nowhere, to be visibly not a real account.
- **Two agents never share a checked-out working tree.** Each works from its own `git worktree`,
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
  this repo is released) **or another agent's own state** — `~/.gemini/` included; editing a file
  there is an install.

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
