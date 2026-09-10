# drunken-guild — instructions for Antigravity

Loaded automatically. Kept short enough that it is actually read.

`SESSION_CHECKPOINT.md` is the other half: **read it at the start of a session.** This file says
how to work; that file says where things stand.

**Antigravity as an active peer on this repo is supported, not recommended.** The rules below
(worktree isolation, the `--author` split, `agent:antigravity` labels) still exist and still hold
if it runs — this is not a removal. But do not assign it work or expect it to pick any up:
`SESSION_CHECKPOINT.md` carries the current decision record (DG-301) and is the authoritative
status. As of that record, the reason is Antigravity's own track record on rules written
specifically for it, plus a permission-prompt noise problem in its own harness (`~/.gemini/`) that
this repo has no way to reach or fix.

---

## What this repo is

**One repository, two deliverables**, and almost every rule below follows from that:

| | what it is | where |
|---|---|---|
| **The runtime** | a Python package — MCP servers (`drunken-jira-mcp`, `drunken-discord-mcp`) and the CLI (`drunken-doctor`, `drunken-away`, `drunken-usage`, …) | `src/`, `tests/`, `scripts/` |
| **The AI layer** | the skills and agents that get installed into `~/.gemini/config/` and read by Antigravity | `skills/`, `agents/`, `templates/`, `examples/` |

It exists because these two were separate repositories that drifted. Skills were authored in four
places with 26 duplicated by name; `git-workflow` silently diverged to 73 lines against 196 while a
just-merged PR told one repo to defer to the other's copy. **One surface is the answer.** Do not
recreate a second one.

*Drunken Programmer* is the pen name; `drunken-guild` is the product. The name says drunk and the
contents are FATAL directives, blast-radius checks and post-mortems. That tension is the brand —
do not soften either half.

### The AI layer stays in git. This is deliberate.

DG-250 says a project's wrapper directory is not a git repository and its AI layer stays out of
git. **That rule does not apply here, and it is not a defect to fix.** Here the AI layer *is* the
product; applying the rule literally moves the deliverable out of version control. A consuming
project's own wrapper directory is the reference implementation of DG-250 — this repo is the
documented exception.

Do not "fix" this repo by moving `skills/` or `agents/` out of git.

---

## Commands

```bash
uv sync --extra dev                 # required, not optional — see below
uv run pytest -q                    # e2e is deselected by default, on purpose
uv run ruff check src/ tests/ scripts/
uv run ruff format src/ tests/
uv run mypy src                     # --strict via pyproject
./scripts/verify_clean_install.sh   # clean-room checks, touches nothing of yours
```

`pytest -m e2e` talks to **live Jira and files real tickets**. Run it deliberately or not at all.
It is deselected because for months it was not, and it filed 52 junk tickets before anyone noticed.

`bandit -ll` and `pip-audit --strict` also gate CI; `uvx bandit -ll -q -r src/` runs it locally.

**`uv sync --extra dev` is required, and a fresh clone does not have it.** Without pytest in
`.venv`, `uv run pytest` falls through to whatever `pytest` is on PATH — a different interpreter,
whose site-packages may carry an editable install claiming `core`, `scripts`, `service` and the
rest. That is not hypothetical: it ran this repository's suite against `~/Projects/drunken-team`
for two rounds of review, green the whole time, with coverage reading 0% because nothing in `src/`
was ever imported (DG-268). `tests/conftest.py` now fails the run at session start rather than
letting it pass, and names the fix.

### Which gates cover which half

The Python gates — `ruff`, `mypy`, `pytest`, `bandit`, `pip-audit` — cover **`src/`, `tests/` and
`scripts/` only.** The AI layer is markdown and has no type checker; what guards it is
`scripts/check_doc_drift.py` and review.

CI knows the difference: a job reports whether any non-markdown file changed, and the test matrix
and clean-install read that. The secret scan and the doc-drift check are **not** gated and run on
every push, because a secret pasted into a README is still a secret.

---

## What a run cost

```bash
uv run drunken-usage --project drunken-guild --by ticket
uv run drunken-usage --project drunken-guild --by model --rates ~/.drunken/usage_rates.json
```

Reads the host's own transcripts — nothing is instrumented, nothing is sent anywhere, and it works
retroactively. `--by ticket` works because a branch named `feature/DG-251-slug` carries its key.

Two things it will not do, both deliberate. **It does not know prices** — rates are an operator
input, and an unpriced model reports no cost rather than a smaller one. **It counts Claude only**;
Antigravity's usage lives under `~/.gemini/`, which is out of bounds, so every report says what it
did not see.

---

## Jira is the source of truth

`TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW**, including for your own work.

**How to write and run a ticket is `skills/kanban/jira-tickets/SKILL.md`** — the
FINDING/SCOPE/ACCEPTANCE shape, the fields this Jira can actually set, and what must be verified
before anything is Done. Read it before opening or closing a ticket. It is the same file
Antigravity is pointed at, so the rules cannot drift apart per agent.

A ticket is scanned, not read: the story of how you found it belongs in the commit and the PR.

Use the `drunken-jira-mcp` tools (`jira_search_issues`, `jira_start_task`, `jira_transition_issue`,
`jira_submit_for_review`, `jira_add_comment`, `jira_assign`, `jira_board_info`,
`jira_move_to_backlog`, `jira_move_to_board`). `scripts/jira_bridge.py` still exists for shell use
but is not the supported path.

One ticket per phase, and each phase must merge on its own without breaking the one before it.

**A ticket marked IN REVIEW is not merged code.** DG-225 sat in review for weeks while its branch
was never merged and the trunk stayed vulnerable; every surface said it was done. Verify against
`origin/develop` before believing any claim that something is fixed.

**There is no local board.** The `board_*` tools are retired and `drunken-board-mcp` is no longer
packaged at all (DG-265) — its code is kept at `_not_used/board-mcp/`, untracked, and nothing
installs it; `RETIRED.md` names the commit it is recoverable from. Do not create `.claude/board/` or `.agents/board/`, and do not author a skill
that reads or writes one. A board beside Jira is a second surface that can disagree with the first.
What is genuinely lost is claim expiry — a Jira assignee never expires, so a ticket left assigned to
an agent that died stays that way until a human looks. That is a ten-second fix, weighed against a
class of silent disagreement that costs weeks.

**The backlog is not a second status.** `jira_move_to_backlog` and `jira_move_to_board` change
membership of the current working set and nothing else. A ticket parked in the backlog is still
`IN PROGRESS` if that is what it was.

**Assignee is the accountable human; the agent doing the typing is a label.** Assignee can only
hold a real email, so it cannot say which agent is on a ticket. A ticket an agent is actively
working carries `agent:claude` or `agent:antigravity` in `labels` — set it, do not repurpose
Assignee for it (DG-293).

---

## Git

**The full rules are one file: `skills/workflow/git-workflow/SKILL.md`.** Branch naming, which merge
strategy belongs to which target, and the release flow all live there. **Load it rather than
reasoning from memory, and do not restate it here** — a second copy of a rule is the failure this
repo was built to cure.

Five things are unrecoverable if you get them wrong, so they are named here as pointers, not as the
rule itself:

- Never push to `main`.
- **An agent opens pull requests; a human merges them.** No exception for your own PR, a one-line
  change, a green CI, or a 👍 that arrived over Discord.
- Never `git merge` locally against `main` or `develop` and push the result.
- Merge strategy is chosen by target, not preference.
- **An agent commit passes `--author`**, so `git log` tells an agent's commit from the operator's:
  `Claude Code <claude@drunken.local>` or `Antigravity <antigravity@drunken.local>` (DG-293). The
  addresses are local-only and resolve nowhere — they exist to be visibly not a real account.
- **Claude and Antigravity never share a checked-out working tree.** Each works from its own
  `git worktree`, on its own branch, so a checkout one switches or edits can never be pulled out
  from under the other (DG-288). Still the rule if Antigravity runs here — see the note at the top
  of this file on why that is currently not recommended.

The `DG-` key in a branch name is not decoration: `drunken-usage --by ticket` reads it back off the
branch and has no other source, so a branch without one reports as untracked cost, silently.

Pre-commit runs ruff, ruff-format, mypy, and a check that blocks committing while the current ticket
has an unresolved Discord approval. Do not bypass it. **Install it in a fresh clone** — a clone
without `.git/hooks/pre-commit` runs no gates at all and says nothing.

---

## Tests

**A test for a bug or a security finding must be seen failing first.** A test written after the fix
proves only that it compiles. Say so in the PR when you have done it.

Match the surrounding test style. Assertions carry the reason they exist, not just the expectation.

---

## Authoring the AI layer

This half has no compiler, so its structure is the only thing keeping it consistent.

### Skill files

Every `SKILL.md` lives at `skills/<category>/<skill-name>/SKILL.md` and follows this shape:

1. YAML frontmatter delimited by `---`, containing `name:` (kebab-case) and `description:`.
   **The description carries the activation triggers** — state when to apply the skill and end with
   the slash command. There is no separate `**Trigger/Keywords:**` line.
2. `# Skill: <Title>`
3. `**Version:**` — optional SemVer.
4. `**Description:**` — one line.
5. `---`
6. A `<system_prompt>` block. `<role>`, `<constraints>` and `<output_format>` are always required;
   `<core_instructions>` or `<execution_rules>` and domain-specific blocks are optional.

**A skill that calls an MCP tool must name the server it requires in `<constraints>`**, so a project
without that server learns why the skill will not run.

### Agent files

Every agent is `agents/<agent-name>.md` with frontmatter carrying `name`, `description`, `model` and
`tools`, then the same `<system_prompt>` block.

### Rules that apply to both

- **English only.** Every description, trigger, instruction, constraint and output format.
- **Never silently delete or overwrite existing logic** when modifying a skill or agent. Preserve
  what is there unless told to remove it.
- **Read the index before loading a skill.** `skills/INDEX.md` and `agents/INDEX.md` list every name
  and path. Do not guess paths from memory. Both are **generated by the install scripts** —
  regenerate them, never hand-edit, because hand-generation drifts.
- `skills/.external` lists skills this repo ships but did not author. **An empty file is a claim
  that there are none, made to everyone who installs a public MIT-licensed repository — not a
  default.** It has been wrong in both directions: it once declared four skills third-party whose
  source was the sibling repo, and the merge then "corrected" it by declaring four *genuinely*
  third-party skills first-party. Read the file; the open question is recorded in it (DG-263).

### Installing is the operator's job, not yours

**Do not run the install scripts, copy files into `~/.gemini/config/` or `~/.gemini/`, or deploy anything.
Installation is always a manual step performed by the Boss.** When a skill or agent is ready, say
so and give the command; do not run it. This rule came from the toolkit side of the merge, where it
was FATAL, and it is FATAL here.

```
scripts/install/install_skills.sh    → ~/.gemini/config/skills/  + the Antigravity tree
scripts/install/install_agents.sh    → ~/.gemini/config/agents/  + the Antigravity variant, generated
scripts/install/install_mcp.sh       → prints or writes a project's MCP config
```

The first two also refresh `INDEX.md`, which is generated *and* committed — so it goes stale on any
change to a skill's name or description, and an agent that must not install had no way to fix a
tracked file. Both take **`--index-only`**: rebuild the repository's index, write nothing anywhere
else. Use that, never a hand edit — hand-generation drifts from the generator's output by a byte or
two per line, which is worse than stale.

**The rename blocks a reinstall until the old package is uninstalled.** `uv tool install .` fails
with *"Executables already exist"* while `drunken-team` still owns those names, and `--force` is
the wrong answer: it repoints the symlinks and leaves the old environment installed, still shipping
a `drunken-board-mcp` this package no longer contains. `uv tool uninstall drunken-team` first.

`install_mcp.sh` is a thin wrapper over `drunken-config` on purpose. `drunken-config` reads the
registry, knows a repository's config from a host application's, and merges rather than overwrites.
A second emitter beside it would be two things answering one question.

### Four layers reach a project, from three places

A skill that does not say which layer it needs gets installed into a project that cannot run it.

1. **Skills** — authored here, installed to `~/.gemini/config/skills/`.
2. **Agents** — authored here, installed to `~/.gemini/config/agents/`.
3. **MCP servers** — also here, in `src/`, declared per project in that project's `.mcp.json`.
4. **Project instructions** — each project's own `CLAUDE.md` / `AGENTS.md`.

**Layers 1 and 2 stand on their own.** Most skills need no MCP server at all. Only the coordination
skills do.

`templates/CLAUDE.md` is a different document from this one: it is the file **other projects copy**.
This one adds the authoring rules, which apply nowhere else. When a coordination rule changes,
change it in both.

---

## Approvals — ask without stopping

Full protocol in `skills/workflow/ask-boss/SKILL.md`; the short version:

- The Boss is reading this conversation → **just ask them here.** Discord is for when they are not.
- Otherwise `request_boss_approval_async(action, reason, ticket_key)`, which returns a `req_id`
  immediately. Park the task, take the next unblocked one, and collect with `check_approvals`
  **when you finish a task or start a session — never mid-task.** Half-applied approvals leave the
  repo in a state nobody can reason about.
- There is no timeout and nothing is killed for going unanswered.
- An approval is bound to the commit it was granted against. From a different HEAD it reads `stale`.
- Force-push, hard reset, `rm -rf` and reading `.env` are denied by `.gemini/settings.json`
  **regardless of what comes back over Discord.** Do not route around it; raise it with the Boss.

## Away mode — the other layer that asks

Everything above is the agent deciding it needs permission. The **harness** also asks, before the
model runs at all. The model never sees that one, which is why saying "I'm going out, send it to
Discord" in chat never worked and never could.

```bash
uv run drunken-away on --note "out until 6"   # prompts go to Discord
uv run drunken-away off                       # back to the terminal
uv run drunken-away status
```

With it on, the PreToolUse hook resolves each call in this order, and the order is the design:

1. **On the deny list → denied.** It never reaches Discord. A 👍 cannot authorise `rm -rf`.
2. `bypassPermissions` mode, or an approval tool → no decision. Asking for permission must not
   itself need permission.
3. **On the allow list → no decision**, not `allow`. The hook never *widens* permission.
4. Not away → no decision. The terminal prompt is the better interface when you are at it.
5. Otherwise → ask on Discord, wait, and map 👍/👎 onto allow/deny.

Three things worth knowing before you turn it on:

- **A timed-out hook does not block the call** — it falls through to the normal permission flow. So
  the hook answers *before* its own deadline (`WAIT_BUDGET_SECONDS`, 25 min) rather than waiting to
  be killed at the `timeout` in `.gemini/settings.json` (30 min). A test asserts the gap; do not
  change one number without the other.
- **`uv run drunken-away off` is allowlisted on purpose** — found the hard way with the agent
  stranded. Do not remove that rule.
- **It is noisy by design.** Widen the allow list deliberately rather than reaching for
  `bypassPermissions`.

---

## Things that will bite you

- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal. Show
  `env://…` or `file://…#key`, never a token, channel id, workspace URL or account email inline.
  gitleaks scans full history and `.env` is deliberately not allowlisted.
- **Config precedence is fixed, and nothing discovers a file by climbing.** Per field: an
  **environment variable** wins, then the **registry**, then the project's own `.agents/*.json`. An
  env var is explicit and named — that is how a container passes a different bot in. A `.env` found
  by walking up the tree is neither, and it used to be loaded into `os.environ` first, so it arrived
  disguised as rule 1 and *outranked* the registry. Nothing reads a `.env` now. `os.getcwd()` plus a
  loop over `os.path.dirname` is the signature — grep for it, do not reason about it.
- **Never let import-time failure be a failure mode.** Anything that can fail must fail inside a
  tool call, so the caller reads a message instead of watching a server vanish. Use
  `core/errors.py` — every error carries a remediation, because "unknown project 'alpha'" only tells
  an agent to give up.
- **An agent does not delete.** Retired things move to `_not_used/` with a note saying why and what
  replaced them, and *marking a thing unused beats removing it*. **`_not_used/` is not committed**
  (DG-291): it is a working directory, and the tracked record is `RETIRED.md` at the root. Add the
  row there in the same change — that row is the only part a fresh clone gets. Publishing the
  directory shipped a 73-line `git-workflow` beside the live 196-line one, and drew Dependabot
  alerts and a merged pull request against withdrawn code. Anything that would need a
  recursive force-delete becomes a **list handed to the Boss to run**. A recorded authorisation from
  an earlier session is not permission to delete today.
- **`drunken-doctor` checks that a credential works, not that a project exists.** It printed
  `OK … (project ALPHA)` while Jira answered *"No project could be found"* (DG-260). Verify a project
  key against the API before trusting a green line.
- **`require_discord()` and `require_jira()` are not symmetric.** `require_jira()` returns a
  resolved object carrying a ready `auth_header`; `require_discord()` returns the **unresolved
  reference string**. The obvious call sends the literal reference as a bearer token and Discord
  answers `401`, which reads exactly like a bad token or a bot that was never invited. Pass it
  through `core.secrets.resolve()` yourself.
- **Every outbound HTTP call goes through `core/http.py`.** One `# nosec`, on the guard itself.
- **Do not touch `~/Projects/drunken-team` or `~/Projects/ai-team-toolkit`.** They are the fallback
  until this repo is released and verified.
- **Do not touch `~/.gemini/antigravity-cli/brain/*/worktrees/`.** That belongs to Antigravity.
- Antigravity reviews and runs client-side acceptance tests. It does **not** edit this repo's source
  while security work is in flight.
