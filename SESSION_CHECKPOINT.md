# Session Checkpoint

Short-term memory and context handoff between AI coding sessions.
**Read this at the start of a session and update it before ending your turn.**

Last updated: 2026-08-13 · `develop` is past **2.2.0**, unreleased · tagging **2.3.0** is the next
milestone

---

## 1. Where things stand

**Active work: "MCP Hardening & Portability"** — shipped as incremental 2.x releases.
Goal: any AI, any tool, running from any directory can use the MCP servers safely, with no project
ever holding a credential.

| | |
|---|---|
| Branch | `develop` @ `5cff91b`, CI 🟢 4/4 |
| Merged 2026-08-13 | DT-238 · DT-242 · DT-241 · DT-243 · DT-244 · DT-239 · DT-245 · DT-240 · DT-246 · **DT-247** (#94) · #95 |
| Open PRs | **none.** `sornbuen15/isac#2` merged 07:41 |
| Jira | DT-249 IN PROGRESS · DT-225 IN PROGRESS (only S1/S2/S8 left) · DT-248 filed · 6 in To Do |

### ⚠️ This section was wrong for four hours — read why before trusting any checkpoint

The version of §1 that shipped in **#95 described the world before #94**, and told its reader to go
and merge a PR that had already landed. The mechanism: **#95 branched from `a33e15e`, before #94,
and merged after it**, so a stale section overwrote a newer one. Nothing conflicted, because only one
side had touched those lines.

This is §5's DT-225 lesson in its other dialect. There it was *a checkpoint on a feature branch
describes that branch, not the trunk*. Here it is **a checkpoint written before a merge describes the
world before that merge, no matter when it lands.** Before believing this section: check the merge
base against `origin/develop`.

**#95 also carried the key `DT-249`, which did not exist in Jira** — a branch named for a ticket
nobody filed, merged without one. `DT-249` now belongs to *this* cleanup, filed after the fact. If
you follow PR #95's branch name to a ticket, that is why it does not describe the same work.

### Next, in order

1. **DT-236** — the PreToolUse hook. **This is what the Boss originally asked for**: "I'm going out,
   send it to Discord", and the terminal still blocks on a permission prompt. Everything it needs
   exists. Boss and Claude agreed it is blocked only on **S6**, which is now done — *not* on all of
   DT-225. S1/S2/S8 do not touch it. *(Jira's own description still claims the DT-225 dependency;
   DT-249 adds a comment correcting it, because the MCP tools can comment but not rewrite a
   description.)*
2. **DT-225 remainder — S1, S2, S8.** Verified still open on `develop` on 2026-08-13, in that order
   of ease. Blocks DT-226 and nothing else.
3. **Tear out the copies of this tooling vendored into TWA and ISAC** (`monitor.py`,
   `jira-lite-cli.py`, `.agents/scripts/*`). Boss authorised it; not started. This is what keeps
   TWA's `.env` needing a token at all.
4. **Two `.env` files still hold the revoked token** — `drunken-team/.env` and `tff-web-app/.env`.
   Nothing of ours reads them any more, but they are traps for anyone running the vendored copies.
   Clearing them follows item 3. Boss has not yet said whether to.
5. **DT-237, then tag 2.3.0** — noting that DT-237 is a *decision* the Boss deferred, so it is worth
   asking whether the tag should wait on it at all. DT-237's own description says doing nothing is a
   legitimate outcome.

### 🔑 The Jira token was rotated on 2026-08-13

`.agents/jira_config.json` in **ISAC** held a live Jira token in plain text, committed in `103794d`
and again in `bb80153` — whose subject is *"Apply security hardening and workflow
standardizations"*. Both were pushed. The repo is private, which is the only reason this was a
cleanup rather than an incident.

The token is **revoked and replaced** (confirmed 401), so what remains in history is inert and no
history rewrite is proposed. Rotation was a single edit — `scripts/set_secret.py jira.default` —
because every project references one entry instead of copying it. That is the whole payoff of the
reference design, and it was earned the hard way: a stale copy in TWA's `.env` had been answering
Jira with an empty board for months.

> **Do not call this work "v3".** Boss ruled it is bugfix + additive throughout. `3.0.0` is reserved
> for when things are *removed*, not when they are added.

> `~/Projects/todo/drunken-team/MCP-ARCHITECTURE.md` is **retired** as the cross-AI channel — Boss's
> call. It was a stopgap for when one AI ran out of tokens; this file does that job. It is not in
> git, is not maintained, and nothing should point at it.

## 2. Boss's four rules — the criteria every decision is judged against

1. Any AI / any tool must be able to use mcp, jira, discord
2. Every change must weigh cyber security **and** implementation flexibility
3. Must work in other projects for real — a particular directory, or the cloud, must not be an
   obstacle. Docker or Kubernetes must be viable
4. We are building a **tool**: if we can use it, others must be able to — safely, and resistant to attack

Anything that violates one of these is out, without further debate.

## 3. Locked decisions

| Topic | Decision |
|---|---|
| Transport | **Dual** — one codebase, `--transport stdio\|http`. stdio default |
| Auth (HTTP) | **Pluggable** — static bearer bound to audience+project day one; OAuth 2.1/OIDC later |
| mcp SDK | Pinned `>=1.28,<2`; migrating to `MCPServer` (2.x) is a separate epic |
| `board_mcp` | **local stdio only** — it is filesystem-bound |
| Secrets | Pluggable resolver, resolved **once at init** and cached (Antigravity §8.2) |
| Git in MCP | **Kept** as workflow coordinator + security gateway, with 3 security conditions (§9.1) |
| Roles | **Claude implements** Phase 1–6; Antigravity reviews and runs client-side acceptance tests (§10.2) |

Architecture is **settled** — Antigravity ACKed all three points in §11. No further consensus rounds.

## 4. Delivered

**2.1.0 (DT-189)** — ten modules under `src/core/`: `paths` (`$DRUNKEN_HOME`, nothing from
`__file__`) · `secrets` (pluggable `env:// file:// op:// keyring://`, resolved once per process,
scheme-less references rejected) · `redact` (masked `Secret`, base64-aware redactor) · `errors`
(`DrunkenError` with remediation, `as_tool_result`) · `registry` v2 (in-memory v1 upgrade, optional
`path`, validated ids) · `context` (`verify_jira_identity`) · `http` (scheme-guarded `urlopen`) ·
`doctor` (`drunken-doctor`) · `init` (`drunken-init`)

**2.2.0 (DT-224)** — the three servers rewired onto `ProjectContext`. `--workspace` is gone,
`jira_mcp/config.py` and its `.env` parent-walk are gone (S3), `drunken-register` is retired (S11).

**Approvals (DT-232, DT-233)** — asking no longer stops the agent. `submit()` returns a handle and
`poll()` collects the answer later; a waiting task parks in the new `blocked` lane carrying the
`req_id` that would free it, and `board_available_tasks` offers only tasks whose dependencies are
done. No deadline and nothing is auto-killed — reminders back off 15 min → 1 h → daily, and survive
a daemon restart. An approval is bound to the commit it was granted against and reads `stale` from
any other HEAD. The blocking `request_boss_approval` still works; `mode` defaults to `sync`, so
anything written by an older daemon behaves exactly as before.

**DT-235** — `drunken-jira-mcp` had `--project` as `required=True`, so argparse killed it with
`sys.exit(2)` before the MCP handshake and the host saw a process that vanished. Principle 8, from
this very file, caught in the wild. `core/errors.py` had existed for it since 2.1.0 and no server
had imported it.

**DT-234** — `jira_create_issue` warns when the project has no agile board. TWA and ISAC are
business-type projects; work filed there succeeds and is then invisible.

**DT-236 — the PreToolUse hook.** The oldest complaint in the project, closed. `drunken-away on`
writes a flag the *machine* can read, and the hook turns each harness permission prompt into a
Discord question. Deny is checked first and never routed; an allowlisted call gets silence rather
than `allow`, because the hook's job is to never widen permission.

Two things the ticket had wrong, both found by reading the contract rather than trusting it:

- The hook timeout default is **600s, not ~60s** as the ticket said.
- **A timed-out hook does not block the call** — it falls through to the normal permission flow, and
  the documentation says outright not to count on a stalled hook as a gate. So the hook answers
  *before* its own deadline instead of waiting to be killed. `WAIT_BUDGET_SECONDS` (1500) and the
  `timeout` in `.claude/settings.json` (1800) are two numbers in two files that must stay in a
  relationship, so a test asserts it — the same shape as S9 and the stale `requirements-dev.txt`.

And one found only by running it, which is §13's whole point. The live acceptance run ended with the
agent **stranded**: away mode was on, the Boss pressed 👎, and `drunken-away off` was itself routed
to Discord along with every `Read` and `Edit` that could have fixed it. A switch that cannot turn
itself off is not a switch. The way out has to be an **allow rule** — hook silence only means "carry
on as normal", and carrying on as normal in an unattended terminal is the blocking prompt this
ticket exists to remove.

Proven end to end against live Discord: 👍 → `allow`, 👎 → `deny` (which blocked the agent's own
tool call through the real harness, not a simulated stdin), and a denylisted `rm -rf` refused in
0.06s without reaching Discord at all — including when hidden behind `git status &&`.

## 5. Findings — S1 to S12

**Fixed in 2.1.0:** S4 (Jira 200 + `[]` on a bad token), S5 (`__file__`-derived paths), S9 (version
drift), S10 (inverted `\n` escaping), S11 (`drunken-register` unusable and writes plaintext tokens
into the project), S12 (e2e tests writing to live Jira), 3 aiohttp CVEs, 3 bandit MEDIUM.

**Fixed in 2.2.0 (DT-224):** S3 (`.env` parent-walk deleted with `jira_mcp/config.py`), S11.

**S6 — closed by DT-241 (2026-08-13).** The socket is created under `$DRUNKEN_HOME` and chmod-ed
`0600` immediately after binding; verified live as `srw-------`. Correcting this file's own
framing while closing it: the socket was never actually reachable by anyone else. Connecting to a
unix socket needs *write* permission, and the usual umask of 022 stripped it. The defect was that
**nothing in the code set the mode at all** — the result depended entirely on the umask of whatever
launched the daemon, and umask 000 would have opened the approval channel to every local process.
Safe by accident is not safe by construction.

**S1, S2 and S8 — closed by DT-225 (2026-08-13).** Each was seen failing first.

| # | Was | Now |
|---|---|---|
| S1 | `query_project_context` did `if os.path.isabs(file_path): resolved = file_path` — no containment check of any kind to traverse *around*. Arbitrary file read | Containment judged on the **resolved** path, both sides. Catches `../`, and catches a symlink that sits inside the project and points out of it — which a string comparison cannot. `access_denied_path_traversal` stays a different answer from `file_not_found`, so a typo does not read as an attack |
| S2 | No authorization anywhere in `board_mcp/server.py`. `main()` said it out loud: *"--project (ignored by board, kept for compat)"* — a server launched for one project served any other on request | **Default deny.** `--project` (or `DRUNKEN_BOARD_PROJECT`) binds the server to one project; an unbound server refuses every call with a remediation. **Behaviour change** — this repo's `.mcp.json` relied on the old "serve them all" and now passes `--project drunken-team`. Antigravity's config already did |
| S8 | `jira_search_issues` passed raw JQL through; `--project` named the project and confined nothing to it | The query is **wrapped**, not validated: `project = "KEY" AND (caller's query)`. Parsing a query language to judge safety is the same losing game as prefix-matching a shell command, and conjunction makes it unnecessary |

Two details in S8 carry the guarantee, and both are tested. The parentheses are not cosmetic —
`project = "DT" AND a OR b` binds as `(project = "DT" AND a) OR b` and the `OR` escapes the scope
entirely. And `ORDER BY` has to be hoisted outside them or the result is not valid JQL; that hoist
is quote-aware, so a ticket whose summary contains the words "order by" is searched rather than
mangled.

Proven against live Jira rather than argued: a cross-project query returned **0 issues**, and
`status = Done OR project = ISAC` returned **50 issues, every one of them DT**. That second one is
the real proof — without the parentheses it would have returned ISAC's.

> **⚠️ HTTP transport (Phase 4 / DT-226) waited on these, and no longer does.** Everything is still
> local stdio; what changed is that opening Phase 4 no longer exposes an arbitrary file read, an
> unbounded board server and an unscoped JQL search along with it. DT-226 should still be reviewed
> on its own merits before it opens.

**How this was missed, because it will happen again otherwise.** The work exists on
`feature/DT-225-security-hardening` and was never merged. Jira said IN REVIEW, that branch's copy of
this file said *"Fixed in 2.3.0"* and *"HTTP transport is now safe to open"* — so every surface
agreed it was done. Nothing checked `develop`. **A ticket in review is not a merged ticket, and a
checkpoint on a feature branch describes that branch, not the trunk.**

## 6. S12 — read this before running the test suite

`test_jira_e2e.py` and `test_full_system_e2e.py` are marked `@pytest.mark.e2e`, and the marker's own
comment says it exists "so it doesn't run on standard unit test runs unless requested" — **but nothing
ever deselected it.** Every plain `pytest` therefore filed two real tickets into the live DT project.
`DT-169` … `DT-223` are all junk; roughly thirty came from this session's own test runs.

Fixed by implementing what the marker always meant: `addopts` deselects `e2e`, and `tests/conftest.py`
skips those tests with a readable reason when credentials are absent. Run them deliberately:

```bash
pytest -m e2e
```

Side effect: the default suite went from ~17s to ~2s, because it no longer calls Atlassian.

**Cleaned up 2026-08-12 (DT-229).** 52 `[E2E TEST]` tickets plus `DT-104` `[SCRATCH]` were archived
to a manifest and then deleted with the Boss's authorisation. DT went from 108 issues to 57.

Correcting this file's own earlier claim, because it sent someone looking in the wrong place: it
said the junk was `DT-169` … `DT-223`, roughly 55 tickets. **50 of those 55 numbers do not exist in
Jira at all**, and the 5 that do are real work. The junk was actually `DT-66` … `DT-130`, and all of
it was already `Done`.

## 7. CI — what it now enforces

Two stacked causes kept it red for two months: the `mcp<2` issue (DT-182), and behind it a stale
hand-maintained `requirements-dev.txt` missing `pytest-asyncio`. Same root cause as S9 — two sources
of truth. CI now installs `-e ".[dev]"`.

**Nobody saw it because the workflow only ran on `main`, while all work lands via PRs into `develop`.**
It now watches both.

| job | gates |
|---|---|
| `test (py3.10)`, `test (py3.13)` | ruff check, ruff format, mypy `--strict`, pytest — **3.10 is the declared floor and had never once been exercised** |
| `security` | `pip-audit --strict`, `bandit -ll` (MEDIUM+), `gitleaks` over full history |
| `clean install` | `scripts/verify_clean_install.sh` |

```bash
./scripts/verify_clean_install.sh
```

Clean-room check anyone can run: wiped environment, scratch `HOME` and `DRUNKEN_HOME`, unrelated cwd,
throwaway venv. Touches nothing of yours. 22 checks.

## 8. Principles that must not be quietly reversed

1. **A reference with no scheme is an error**, not a literal — otherwise someone eventually pastes a
   real token into the committable registry and it *works* until it is pushed. `literal://` is the
   greppable opt-out.
2. **`path` is optional** — a containerised server has no host checkout to name.
3. **A v1 registry is upgraded in memory and never rewritten**, so downgrading is just running the old
   code rather than a one-way door.
4. **A corrupt registry reads as empty instead of raising** — raising at startup recreates §1.1, where
   the server vanished and said nothing. `doctor` is what says it out loud.
5. **Redaction catches the base64 `Basic` form** — `jira_client` encodes `email:token` into the header.
6. **The gitleaks allowlist keys on a marker, not a path.** "Skip `tests/`" would make the scan pass
   while removing the protection, and tests are exactly where a real token gets pasted. `.env` is
   deliberately not allowlisted.
7. **Every outbound HTTP call goes through `core/http.py`** — one `# nosec`, on the guard's own urlopen.
8. **Never let import-time failure be a failure mode** — anything that can fail must fail inside a tool
   call, so the agent sees a message instead of a server that silently disappeared.

## 9. Next phases

| version | work |
|---|---|
| **2.1.0** | ✅ DT-189 — `core/` foundation |
| **2.2.0** | ✅ DT-224 — `--workspace` → `--project`, `ProjectContext` wired in, S3 and S11 closed |
| — | ✅ DT-232 / DT-233 async approval · DT-234 board warning · DT-235 jira-mcp startup |
| **2.3.0** | ✅ DT-238 docs · DT-242 registry works end to end · DT-241 state paths + **S6** · DT-243 cwd paths + snapshot recovery · DT-244 retire the `agy` name · DT-239 wire `as_tool_result` · DT-245 onboard TWA and ISAC · DT-240 CI doc-drift check · DT-246 daemon and Antigravity reach the registry |
| — | ✅ DT-247 — Discord config from the registry, and TWA's last stale token (#94) |
| — | ⬜ DT-249 docs/Jira truth alignment · DT-237, then **tag 2.3.0** |
| **2.4.0** | 🟡 **DT-236 — the PreToolUse hook. The thing Boss actually asked for.** Built and proven live; see §4 |
| — | DT-225 remainder: S1, S2, S8 |
| **later** | DT-226 dual transport + bearer auth — the change that makes S1/S2/S8 remotely reachable, so it waits on them |
| ~~2.5.0~~ | ~~Discord daemon multi-tenant~~ — **DT-227 cut.** Boss: nobody drives more than one project at a time, and doing so burns tokens for nothing. One channel serves all |
| **3.0.0** | Removals only: migrate to the mcp 2.x SDK. `--workspace` and `AGY_DAEMON_SOCKET` are already gone (DT-224, DT-244) |

## 10. Outstanding debt

1. **`main` is 7 commits behind `develop`** and has 7 it does not — nothing since 2.1.0 has been
   released. This is a release decision, not drift. *(The old entry here said local `main` had
   diverged from `origin/main` by 20 files. It has not: both are `3d18c2e`, 0 ahead, 0 behind.
   DT-230 closed as stale.)*
2. **24 bandit LOW findings** — mostly `try/except/pass` in `service/`. Not gated, not hidden.
3. **`uv tool install` ignores `uv.lock`** — the tool env has mcp 1.29.0 while the lock pins 1.28.1.
   Both satisfy `<2`, but drift inside the range is still possible. Phase 6's generator should emit
   `--with-requirements`.
4. **The `.claude/settings.json` denylist now has a second enforcer** — DT-236's hook checks it
   before anything else and refuses to route a denied call to Discord at all. Note what that is and
   is not: matching a shell command by prefix cannot be made sound (`rm -rf` and `rm -r -f` are the
   same action, spelled differently), so `core/permission_rules.py` documents itself as a soft
   control and leans every ambiguity toward asking a human. Deny matching is greedy — no word
   boundary, every segment of a compound command, command substitutions included. Allow matching is
   strict, and a compound command is allowed only when *every* segment is.
5. **Two `.env` files still hold the revoked Jira token** — `drunken-team/.env` and
   `tff-web-app/.env`. Nothing of ours reads them since #94, but they are live traps for
   anyone who runs the old tooling. Boss has not said whether to clear them.
6. **TWA and ISAC each carry a vendored copy of this tooling** — `monitor.py`, `jira-lite-cli.py`,
   `.agents/scripts/{jira_bridge,ask_boss,discord_listener,register_project}.py`. They are why
   TWA's `.env` still needs a token at all. Boss authorised tearing them out; not started.
7. **`drunken-doctor` cannot see any of that.** Every failure this session was found by running
   something and looking, not by a check. A `doctor --all` that walks every registered project and
   reports the drift would have caught the dead TWA token, the missing Discord channels and the
   unwired Antigravity config on its own. Not ticketed yet; it is the widest gap in our own tooling.
8. **`scripts/check_doc_drift.py` cannot catch a claim that stopped being true.** It reported 60
   documents clean while CLAUDE.md stated that `drunken-board-mcp` was not wired up — false since
   DT-242. It matches names that were retired, which is a different thing. Widening it is a decision,
   not an oversight: a checker that reads prose is a checker that cries wolf.
9. **`$DRUNKEN_HOME/agy_pids.json` is orphaned state** left over from before DT-244 renamed it to
   `pids.json`. Both files exist. Harmless, and deliberately not deleted under a docs ticket.

## 11. Working agreements

- Jira is SSOT: `TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW.**
- One Jira ticket per phase; each phase merges independently without breaking the one before it.
- A test for a security finding must be **seen failing first**, to prove it has teeth.
- Never put absolute paths in another project's `.mcp.json` — it leaks into git.
- No identity, token, or secret may ever enter a commit.
- **Do not touch or archive `.agents/` files or `~/.gemini/antigravity-cli/brain/*/worktrees/`.**
- Antigravity does **not** edit `drunken-team` source during this work — a merge conflict inside a
  security boundary is the easiest way for a hole to slip through.
- **Approvals (DT-232 / DT-233).** The old "Silent Wait Protocol" — writing `.agents/discord_outbox.json`
  and approving through IDE `run_command` — stays **retired**; that file is daemon state, not an API.
  - In a live session where the Boss can read the conversation, **just ask them there.** Discord is for
    when they are not watching.
  - Unattended, ask with **`request_boss_approval_async`**, then `board_block_task` to park the task and
    move on to whatever `board_available_tasks` offers. **Asking must never stop the other work.**
  - Collect answers with `check_approvals` **when a task finishes and at session start — never mid-task.**
    Acting on an approval the moment it lands is how a repo ends up half-changed.
  - **There is no timeout and nothing is killed for going unanswered.** Reminders back off (15 min → 1 h →
    daily) and the request survives daemon restarts. A question the Boss hasn't reached is not an error.
  - An approval is bound to the commit it was granted against; from a different HEAD it reads `stale` and
    must be re-asked. A yes given this morning does not authorise tonight's different code.
  - Force-push, hard reset, `rm -rf`, and reading `.env` are refused by `.claude/settings.json` **no matter
    what comes back over Discord.** Remote approval is only safe while some actions sit outside it.
  - `request_boss_approval` (blocking, escalates after 2 reminders) still works and is kept until 3.0.0.
    Prefer the async pair; reach for it only when nothing else could possibly be done meanwhile.

## 12. Verified numbers

On `develop` @ `a33e15e` plus PR #94, 2026-08-13:

```
501 tests passed (2 deselected)   ·   Python 3.10 and 3.13
ruff check / ruff format / mypy --strict          clean
bandit -ll / pip-audit --strict / gitleaks        clean
scripts/check_doc_drift.py                        60 documents, clean
scripts/verify_clean_install.sh                   22/22
CI on PRs #85 … #94                               4/4 green each
```

## 13. The acceptance run — and why the numbers above are not enough

Every real defect this session was found by **running the thing**, never by the suite. 465 tests
passed while `as_tool_result` published `jira_search_issues(args, kwargs)` to the host and every
call failed. The suite calls the functions directly, where `*args` accepts anything; an MCP probe
is what caught it. Run this before believing anything is finished:

```
                     drunken-team   twa        isac
drunken-doctor       14 ok          13 ok      14 ok      0 failed
MCP over stdio       6 tools        6 tools    6 tools
  jira_search        50 issues      39 issues  50 issues
Discord /project     6 To Do        0 To Do    2 To Do
bare run in dir      6 To Do        0 To Do    2 To Do    ← needs #94
Antigravity          3 servers, 25 tools, under `env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin`
```

TWA's `0 To Do` is correct — all 39 of its issues are Done. The point is that it no longer means
*"the credential is dead"*, which is what it meant for months.

**The GUI PATH trap, twice.** A host config read by an application launched from `/Applications`
inherits launchd's minimal `PATH`, so a bare command name resolves when you test it in a terminal
and fails inside the IDE. `setup_daemon_service.py` documents this for `uv`; DT-246 walked into it
again for the MCP servers. Hence: **a repository's `.mcp.json` gets a bare name** (committed,
shared, must not carry one machine's layout), **a host's config gets an absolute path** (in `$HOME`,
never committed). Resolution prefers `~/.local/bin` over `shutil.which`, because `uv run` puts the
project's own venv first and writing *that* into a host config works until the venv is rebuilt.

Proven against **live Jira** rather than argued:

- **S4, three times now** — a dead token returns HTTP 200 and `[]`, never an error. It hid TWA's
  expired credential for months, it hid ISAC's missing config, and it was still hiding
  `drunken-team`'s revoked token on `develop` at the time of writing. `verify_jira_identity` asks
  `/rest/api/3/myself`, which 401s. **Never health-check with a search.**
- **DT-234** — DT, TFH and DC stay silent; TWA and ISAC warn. Every board on the site was surveyed:
  **none supports sprints**, and for DT the agile backlog is a strict subset of the board, so
  nothing is stranded. No sprint support is needed anywhere.
