# drunken-team — instructions for Claude Code

Loaded automatically by Claude Code. Keep it short enough that it is actually read.

`SESSION_CHECKPOINT.md` is the other half of this: **read it at the start of a session.** It says
what is merged, what only *looks* merged, and what to pick up next. This file says how to work; that
file says where things stand.

## Commands

```bash
uv run pytest -q                    # 2s -- e2e is deselected by default, on purpose
uv run ruff check src/ tests/
uv run ruff format src/ tests/
uv run mypy src                     # --strict via pyproject
./scripts/verify_clean_install.sh   # 22 clean-room checks, touches nothing of yours
```

`pytest -m e2e` runs the tests that talk to **live Jira and file real tickets**. Run it deliberately
or not at all. It is deselected because for months it was not, and it filed 52 junk tickets before
anyone noticed — see §6 of the checkpoint.

`bandit -ll` and `pip-audit --strict` also gate CI; `uvx bandit -ll -q -r src/` runs it locally.

## What a run cost (DT-95)

```bash
uv run drunken-usage --project drunken-team --by ticket
uv run drunken-usage --project drunken-team --by model --rates ~/.drunken/usage_rates.json
```

Reads the host's own transcripts — nothing is instrumented, nothing is sent anywhere, and it works
retroactively over sessions already on disk. `--by ticket` works because a branch named
`feature/DT-251-slug` carries its key.

Two things it will not do, both deliberate. **It does not know prices.** Rates are an operator input
(`{model: {input, output, cache_read, cache_creation}}`, USD per million tokens); without them you
get tokens, which are a fact. A model that is unpriced — or priced incompletely — reports no cost
rather than a smaller one. **It counts Claude only.** Antigravity's usage lives under `~/.gemini/`,
which is out of bounds by the rule below, so every report says what it did not see.

## Jira is the source of truth

`TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW**, including for your own work.

**How to write and run one is `.agents/skills/jira-tickets/SKILL.md`** — the FINDING/SCOPE/ACCEPTANCE
shape, the fields this Jira can actually set, and what must be verified before anything is Done.
Read it before opening or closing a ticket. It is the same file Antigravity is pointed at, so the
rules cannot drift apart per agent. A ticket is scanned, not read: the story of how you found it
belongs in the commit and the PR.

Use the `drunken-jira-mcp` tools (`jira_search_issues`, `jira_start_task`, `jira_transition_issue`,
`jira_submit_for_review`, `jira_add_comment`, `jira_assign`). `scripts/jira_bridge.py` still exists
for shell use, but the MCP tools are the supported path.

One ticket per phase, and each phase must merge on its own without breaking the one before it.

**A ticket marked IN REVIEW is not merged code.** DT-225 sat in review for weeks while its branch was
never merged and the trunk stayed vulnerable; every surface said it was done. If a ticket claims
something is fixed, verify against `origin/develop` before believing it.

## Git

Work lands on `develop` through a PR. Never push to `main` — `main` is deliberately behind and stays
that way until the current work is finished. Branch as `feature/DT-123-slug`, `bugfix/...`, `chore/...`,
`docs/...`.

Do not stack a PR on another PR's branch: when the base merges and is deleted, GitHub closes the
stacked one. Branch from `develop` and cherry-pick if you need something that has not landed yet.

Pre-commit runs ruff, ruff-format, mypy, and a check that blocks committing while the current
ticket has an unresolved Discord approval. Do not bypass it.

## Tests

**A test for a bug or a security finding must be seen failing first.** A test written after the fix
proves only that it compiles. Say so in the PR when you have done it.

Match the surrounding test style. Assertions carry the reason they exist, not just the expectation.

## Approvals — ask without stopping

Full protocol in `.agents/skills/ask-boss/SKILL.md`; the short version:

- The Boss is reading this conversation → **just ask them here.** Discord is for when they are not.
- Otherwise `request_boss_approval_async(action, reason, ticket_key)`, which returns a `req_id`
  immediately. Park the task, take the next unblocked one, and collect with `check_approvals` **when
  you finish a task or start a session — never mid-task.** Half-applied approvals leave the repo in a
  state nobody can reason about.
- There is no timeout and nothing is killed for going unanswered. Reminders back off 15 min → 1 h →
  daily and survive a daemon restart.
- An approval is bound to the commit it was granted against. From a different HEAD it reads `stale`
  and must be asked again.
- Force-push, hard reset, `rm -rf`, and reading `.env` are denied by `.claude/settings.json`
  **regardless of what comes back over Discord.** Do not route around it; raise it with the Boss.

`request_boss_approval` (blocking) still works and is kept until 3.0.0. Prefer the async pair.

## Away mode — the other layer that asks (DT-236)

Everything above is the agent deciding it needs permission. The **harness** also asks, before the
model runs at all: *"Allow this tool call?"* The model never sees that one, which is why saying
"I'm going out, send it to Discord" in chat never worked and never could.

`drunken-away` is the switch that reaches the machine:

```bash
uv run drunken-away on --note "out until 6"   # prompts go to Discord
uv run drunken-away off                       # back to the terminal
uv run drunken-away status
```

With it on, the PreToolUse hook resolves each call in this order, and the order is the design:

1. **On the deny list → denied.** It never reaches Discord. A 👍 cannot authorise `rm -rf`.
2. `bypassPermissions` mode, or an approval tool → no decision. Asking for permission must not
   itself need permission.
3. **On the allow list → no decision**, not `allow`. The hook never *widens* permission; the
   harness's own list already covers it.
4. Not away → no decision. The terminal prompt is the better interface when you are at it.
5. Otherwise → ask on Discord, wait, and map 👍/👎 onto allow/deny.

Things worth knowing before you turn it on:

- **A timed-out hook does not block the call** — it falls through to the normal permission flow. So
  the hook answers *before* its own deadline (`WAIT_BUDGET_SECONDS`, 25 min) rather than waiting to
  be killed at the `timeout` in `.claude/settings.json` (30 min). A test asserts the gap; do not
  change one number without the other.
- **`uv run drunken-away off` is allowlisted on purpose.** Away mode routes everything else,
  including the command that would switch it off — found the hard way during DT-236's acceptance
  run, with the agent stranded. Do not remove that rule.
- **It is noisy by design.** Anything not on the allow list becomes a Discord question, `Edit` and
  `Write` included. If that is too much for a long unattended run, widen the allow list deliberately
  rather than reaching for `bypassPermissions`.

## Things that will bite you

- **No secret ever enters a commit.** A reference without a scheme is an error, not a literal.
  gitleaks scans full history and `.env` is deliberately not allowlisted.
- **Config precedence is fixed, and nothing discovers a file by climbing (DT-254).** Per field:
  an **environment variable** wins, then the **registry**, then the project's own
  `.agents/*.json`. An env var is explicit and named — that is how a container passes a different
  bot in. A `.env` found by walking up the tree is neither, and it used to be loaded into
  `os.environ` first, so it arrived disguised as rule 1 and *outranked* the registry. Nothing reads
  a `.env` now; source one deliberately before starting the daemon if you want it. `os.getcwd()`
  plus a loop over `os.path.dirname` is the signature — grep for it, do not reason about it.
- **Never let import-time failure be a failure mode.** Anything that can fail must fail inside a tool
  call, so the caller reads a message instead of watching a server vanish. Use `core/errors.py` —
  every error carries a remediation, because "unknown project 'twa'" only tells an agent to give up.
- **An agent does not delete.** Boss's standing rule. Anything that would need a recursive
  force-delete becomes a **list handed to the Boss to run**, and *marking a thing unused beats
  removing it*. A recorded authorisation from an earlier session is not permission to delete today —
  the vendored-tooling teardown was authorised weeks before anyone noticed that TWA's copies sit
  outside any git repository. See §10.6 of the checkpoint.
- **Do not touch `.agents/` state files or `~/.gemini/antigravity-cli/brain/*/worktrees/`.** Those
  belong to Antigravity. `.agents/skills/` is tracked and editable; the rest is not yours.
- **Every outbound HTTP call goes through `core/http.py`.** One `# nosec`, on the guard itself.
- Antigravity reviews and runs client-side acceptance tests. It does **not** edit this repo's source
  while security work is in flight.

## How a project is laid out (DT-250)

Boss's rule, and it applies to **every** project including this one. Three parts, never mixed, and
**only the source code goes to git**:

```
~/Projects/<project>/          wrapper — NOT a git repository
├── <source-repo>/             the git repo. source code only
├── .mcp.json                  drunken-team config. the host looks for it here, so here it stays
├── .claude/ or .agents/       the project's AI layer: instructions, agents, board
└── _not_used/                 parked, never deleted — see the rule above
```

Register the offset or nothing git-related works:

```bash
uv run drunken-init --project <id> --path ~/Projects/<project> --git-root <source-repo>
```

`--git-root` is what tells `ProjectContext.git_root_path()` where `git` actually runs. Without it
`drunken-doctor` reports *"…is not a git repository"* — which under this layout is a **correct
observation about the wrapper and the wrong question**, not a defect to fix in the code.

**TWA is the reference implementation.** `~/Projects/tff-web-app` is the wrapper, `twa/` is the repo,
nothing at the wrapper level is in git, and `drunken-doctor --project twa` reads 14 ok / 0 warnings.
ISAC is the counter-example: it *is* the repo, with 47 files of AI layer committed inside it.

## There is no local board (DT-250)

**Jira is the only coordination surface.** The **assignee** says whose work a ticket is, the
**status** says where it is. Nothing else tracks either.

```
jira_assign(issue_key, "me")            # this one is mine
jira_assign(issue_key, "Jakkawan")      # hand it over — name, email, or "none"
jira_transition_issue(key, "In Review")
```

### The backlog is not a second status (DT-251)

A board can also have a **backlog**, and `jira_board_info` says whether this one does — probed, not
inferred from the board's `type`, because the two do not track each other. `jira_move_to_backlog`
and `jira_move_to_board` move work between the two.

**Neither changes status.** A ticket parked in the backlog is still `IN PROGRESS` if that is what it
was. Backlog membership answers *"is this in the current working set"*, and nothing else — read it
as a status and you have recreated the two-surfaces problem DT-250 just closed.

The agile endpoints underneath take any issue key from any project and move it, board id
notwithstanding. Keys are therefore checked against the server's own project before the call —
same rule as S8, and the same reason.

`drunken-board-mcp` still exists and is **not wired into any project.** It is marked unused rather
than removed, per the rule above. Do not reintroduce it, and do not create `.claude/board/` or
`.agents/board/` in any project.

Why it went: a local board sitting next to Jira is a *second surface that can disagree with the
first*, which is the failure this repo spent a whole session curing — four surfaces disagreeing in
DT-249, one credential copied to three places in DT-248. The evidence was already on disk. This
project's own board held three cards, last touched 2026-07-22, still using the `DAGY-` prefix that
DT-244 retired; every real ticket of that period went through Jira and never touched it.

What is genuinely lost: the board expired a claim after 1800 s and released it, and a Jira assignee
never expires. A ticket left assigned to an agent that died stays that way until a human looks. That
is a ten-second fix by a human, weighed against a class of silent disagreement that costs weeks.
