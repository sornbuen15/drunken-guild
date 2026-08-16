# Session Checkpoint

Short-term memory and context handoff between AI coding sessions.
**Read this at the start of a session and update it before ending your turn.**

Last updated: 2026-08-16 · `develop` is past **2.2.0**, unreleased · tagging **2.3.0** is the next
milestone

---

## 1. Where things stand

**Active work: "MCP Hardening & Portability"** — shipped as incremental 2.x releases.
Goal: any AI, any tool, running from any directory can use the MCP servers safely, with no project
ever holding a credential.

| | |
|---|---|
| Branch | `develop` @ `cc3b07f`, 578 tests green · `feature/DT-251-board-backlog` @ `b577e07`, 625 green |
| Merged 2026-08-13 | DT-238 · DT-242 · DT-241 · DT-243 · DT-244 · DT-239 · DT-245 · DT-240 · DT-246 · **DT-247** (#94) · #95 · **DT-249** (#96, #99) · **DT-236** (#97) · **DT-225** (#98) · **DT-250** (#100, #102) |
| Open PRs | **#103 — DT-251**, board capability + backlog moves. Awaiting the Boss |
| Jira | **DT-225 and DT-236 both closed** · DT-227 closed as cut · DT-251 filed and In Review · DT-95/226/228/237/248 in To Do |

**⚠️ DT-249 and DT-250 are still `In Review` in Jira although #99, #100 and #102 all merged.** This
is §5's lesson running backwards: there, a ticket said IN REVIEW while nothing was merged; here the
code is on the trunk while Jira still says it is being looked at. Same cost either way — a surface
that disagrees with `origin/develop`. Closing them needs the Boss; the agent's transition was
refused by the permission classifier and was deliberately not routed around.

**DT-225 is done in full** — S6 went with DT-241, S1/S2/S8 with #98. **DT-236 is done** — the thing
the Boss originally asked for, working and proven against live Discord. The two oldest open items in
this project both closed on the same day.

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

1. **Refresh the installed tool environment — do this before believing anything is deployed.**
   `~/.local/bin/drunken-*` symlinks into `~/.local/share/uv/tools/drunken-team/`, and **that is what
   Antigravity's `mcp_config.json` launches.** Checked after #97 and #98: `core.permission_rules`,
   `core.away`, `service.approval_hook` and `jira_mcp.jql` are all absent there, and
   `board_mcp.server` has no `_authorize`. **Merging a security fix does not deploy it to the host
   that actually runs it.** Until it is reinstalled, Antigravity's board server still serves any
   project. Same family as §10.3, but with teeth.
2. **DT-250 — the three-part project layout.** Boss's rule: source code, drunken config and the AI
   layer never mix, and only source goes to git. Applies to this repo too. **TWA is done** and is now
   the reference implementation; **ISAC needs the Boss to run the history rewrite** — see §14.
3. **Two `.env` files still hold the revoked token** — `drunken-team/.env` and `tff-web-app/.env`.
   Nothing of ours reads them, but they are traps for anyone running the vendored copies. Same rule:
   the Boss clears them, not an agent.
4. **DT-237, then tag 2.3.0** — noting that DT-237 is a *decision* the Boss deferred, so it is worth
   asking whether the tag should wait on it at all. DT-237's own description says doing nothing is a
   legitimate outcome.
5. **DT-226** is no longer blocked by S1/S2/S8, and is not thereby approved. Review it on its own
   merits before opening a transport.

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
| `board_mcp` | **retired, DT-250.** No project wires it. Jira is the only coordination surface — assignee says whose, status says where. Kept on disk, marked unused |
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
| — | ✅ DT-249 — docs/Jira truth alignment (#96) |
| — | ⬜ DT-237, then **tag 2.3.0** |
| — | ✅ DT-250 — three-part layout, and the local board retired (#100, #102) |
| — | ⬜ **DT-251 — the board's real capabilities, and board ↔ backlog moves (#103)**. See §15 |
| **2.4.0** | ✅ **DT-236 — the PreToolUse hook. The thing Boss actually asked for** (#97). Proven against live Discord; see §4 |
| — | ✅ **DT-225 closed in full** — S6 with DT-241, S1/S2/S8 with #98 |
| **later** | DT-226 dual transport + bearer auth. No longer *blocked* by S1/S2/S8, and not thereby approved — review it on its own merits before opening a transport |
| ~~2.5.0~~ | ~~Discord daemon multi-tenant~~ — **DT-227 cut.** Boss: nobody drives more than one project at a time, and doing so burns tokens for nothing. One channel serves all |
| **3.0.0** | Removals only: migrate to the mcp 2.x SDK. `--workspace` and `AGY_DAEMON_SOCKET` are already gone (DT-224, DT-244) |

## 10. Outstanding debt

1. **`main` is 7 commits behind `develop`** and has 7 it does not — nothing since 2.1.0 has been
   released. This is a release decision, not drift. *(The old entry here said local `main` had
   diverged from `origin/main` by 20 files. It has not: both are `3d18c2e`, 0 ahead, 0 behind.
   DT-230 closed as stale.)*
2. **24 bandit LOW findings** — mostly `try/except/pass` in `service/`. Not gated, not hidden.
3. **The installed tool environment is a separate deployment, and nothing updates it.** This is the
   worst entry on this list. `~/.local/bin/drunken-*` symlinks into
   `~/.local/share/uv/tools/drunken-team/`, and **that is what Antigravity's `mcp_config.json`
   launches** — not this checkout. Verified straight after #97 and #98 merged:

   ```
   core.permission_rules   ABSENT      core.away               ABSENT
   service.approval_hook   ABSENT      jira_mcp.jql            ABSENT
   board_mcp.server._authorize  False
   ```

   So **merging a security fix does not deploy it to the host that actually runs it.** Until that env
   is reinstalled, Antigravity's board server still serves any project on request. The older half of
   this entry is the same shape and still true: `uv tool install` ignores `uv.lock`, so the tool env
   has mcp 1.29.0 while the lock pins 1.28.1 — both satisfy `<2`, but drift inside the range is
   possible, and Phase 6's generator should emit `--with-requirements`.
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
   TWA's `.env` still needs a token at all.

   **This was surveyed on 2026-08-13 and is not a delete job.** Three things an earlier
   authorisation could not have accounted for:

   - **`~/Projects/tff-web-app` is not a git repository.** The repo is the `twa/` subdirectory, so
     `monitor.py`, `jira-lite-cli.py`, `.agents/` and `.env` at that root are unversioned. Removing
     them is unrecoverable. *(The registry also points `twa` at the non-repo parent.)*
   - **ISAC has uncommitted work in a file on the list** — `.agents/scripts/jira_bridge.py` carries
     a fix for the S10 inverted-`\n` bug and a status-filter change, neither committed.
   - **ISAC's uncommitted `.agents/AGENTS.md` instructs agents to use `jira_bridge.py` and *not* the
     board MCP.** Antigravity's ISAC workflow depends on the vendored copy right now.

   Also note this file's teardown list named `.agents/scripts/*` while `CLAUDE.md` says not to touch
   `.agents/` at all. Those two contradicted each other; `CLAUDE.md` wins.

   **Boss's standing rule (2026-08-13): an agent does not delete.** Anything needing removal becomes
   a list for the Boss to run, and marking something unused is preferred over removing it.
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
  - Force-push, hard reset, recursive force-delete, and reading `.env` are refused by
    `.claude/settings.json` **no matter what comes back over Discord**, and since DT-236 the hook
    refuses them before Discord is even asked. Remote approval is only safe while some actions sit
    outside it.
- **An agent does not delete. Boss's standing rule, 2026-08-13.** Anything that would need a
  recursive force-delete becomes a **list handed to the Boss to run**, and *marking a thing unused is
  preferred over removing it*. A recorded authorisation from an earlier session does not license a
  deletion today — see §10.6, where the survey found unversioned files and uncommitted work that no
  earlier authorisation could have known about.
  - `request_boss_approval` (blocking, escalates after 2 reminders) still works and is kept until 3.0.0.
    Prefer the async pair; reach for it only when nothing else could possibly be done meanwhile.

## 12. Verified numbers

On `develop` @ `bb8a37a` — #96, #97 and #98 all merged, 2026-08-13:

```
578 tests passed (2 deselected)   ·   was 501 before this session's three PRs
ruff check / ruff format / mypy --strict          clean
bandit -ll                                        clean
scripts/check_doc_drift.py                        60 documents, clean
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
bare run in dir      5 To Do        0 To Do    2 To Do
Antigravity          3 servers, 25 tools, under `env -i PATH=/usr/bin:/bin:/usr/sbin:/sbin`
```

Re-run in full on `bb8a37a`, 2026-08-13. Every number matches the previous run except DT's To Do,
which is 5 rather than 6 because DT-227 was closed as cut the same day.

Added by this session, proven through real MCP stdio rather than the suite:

```
S8  project = ISAC, asked from drunken-team        0 issues
S8  status = Done OR project = ISAC                50 issues, every one DT
S2  bound to drunken-team, asked for drunken-team  served
S2  bound to drunken-team, asked for isac          refused, names the binding
S2  unbound, asked for anything                    refused, says how to bind
```

TWA's `0 To Do` is correct — all 39 of its issues are Done. The point is that it no longer means
*"the credential is dead"*, which is what it meant for months.

**Running the thing has its own ways to be wrong.** Three false negatives in this session's
acceptance run, none of them a product defect:

1. The `0 failed` in `drunken-doctor`'s summary line was counted *as* a failure by the grep reading it.
2. `uv run --directory X` overrides the `cd` before it, so three projects were all probed from one
   directory and returned identical answers.
3. **zsh does not word-split an unquoted parameter.** `$args` holding `--project drunken-team`
   arrives as a *single* argv entry, argparse ignores it, and the S2 boundary looks broken when it
   is not. This one reproduced twice and was nearly reported as a real bug.

4. **The agile API's reads lag its writes by a beat**, and `GET /board/{id}/issue` on a team-managed
   board returns *backlog* issues too, so it is not a membership test. DT-251's first round-trip run
   therefore showed each move landing one step late and looking inverted, which read as swapped
   endpoints. Re-run with settle time, reading only the backlog list, it is clean.

All four failed *safe* — they under-reported success. The lesson is not to trust a harness more than
the thing it is testing: pass argv as an array, keep `timeout` outside `env -i`, and read the summary
line rather than grepping for a word that appears in it.

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

## 14. DT-250 — the three-part layout, and what ISAC still needs

Boss's rule, 2026-08-13. Every project has three parts that must not mix, and **only the source code
goes to git**: the source, the drunken-team config, and that project's AI layer. It applies to
`drunken-team` itself.

```
~/Projects/<project>/          wrapper — NOT a git repository
├── <source-repo>/             the git repo. source code only
├── .mcp.json                  drunken config — the host looks here, so it stays here
├── .claude/ or .agents/       AI layer: instructions, agent definitions, board
└── _not_used/                 parked, never deleted
```

### TWA — done, and now the reference

`~/Projects/tff-web-app` was already the right shape by accident: it is not a repository, the repo is
`twa/`, so everything at the wrapper was already outside git. What it needed was tidying. Fourteen
entries moved into `_not_used/{vendored,build-artifacts,backups}/` — **moved, not deleted**, with a
README explaining what replaced each one.

The last warning turned out not to be a defect. `drunken-doctor` said *"…is not a git repository"*
about the wrapper, and the remediation text already named the fix: the registry has a per-project
`git_root` offset, added for exactly this case, and TWA's entry never set it.

```bash
uv run drunken-init --project twa --git-root twa
```

**`drunken-doctor --project twa`: 14 ok, 0 warnings, 0 failed.** A bare `jira_bridge.py` run from the
wrapper still resolves TWA. No drunken-team code changed — the architecture was already supported,
just unconfigured. Worth remembering before "fixing" the next warning that turns out to be a question
asked of the wrong path.

### TWA — what is deliberately left

`.agents/` still holds its own copy of the vendored scripts, and **`.agents/AGENTS.md` and
`.agents/skills/ask-boss/SKILL.md` instruct Antigravity to run them.** Moving the scripts before
those instructions change breaks Antigravity mid-flight. `.agents/` is also Antigravity's by the rule
in `CLAUDE.md`. The order is: fix the instructions first, then the scripts are unreferenced and can
be parked.

Also at the wrapper, untouched and for the Boss: `.claude/jira_token.json` (not opened), a TLS
private key `172.20.10.3+2-key.pem` beside its certificate, and `.env` with the revoked token.

### ISAC — every remaining step is the Boss's

ISAC is the counter-example: it *is* the repo, with **47 files of AI layer committed inside it** —
instructions, 13 subagent definitions, `mcp_config.json` and the vendored scripts.

Boss asked whether to start a new repo. **Recommended against.** ISAC has 76 commits since
2026-06-08 and only **15 touch `.agents/`**. A new repo discards 76 commits of real source history,
plus issues, PR #2 and every link, to solve a problem caused by 15. `git filter-repo` gets the clean
result *and* keeps the history.

It also closes DT-248's largest open item for free: `.agents/jira_config.json` is still in history
across 4 commits including `103794d` and `bb80153`. DT-248 declined a rewrite because purging an
inert token cost more than it protected — if the history is being rewritten anyway for structural
reasons, that cost is already paid.

The steps, **all of them for the Boss to run** — see why below:

1. **Save the in-flight work first.** It includes the S10 escaping fix.
   `git add .agents/scripts/jira_bridge.py .agents/AGENTS.md`, commit, push.
2. **Full backup before rewriting anything.**
   `git clone --mirror ~/Projects/isac ~/Projects/isac-backup-YYYYMMDD.git`
3. **Lift the AI layer out** to where it will live, outside git.
   `cp -R ~/Projects/isac/.agents ~/Projects/isac-ai-layer`
4. **Remove it from all 76 commits.**
   `git filter-repo --path .agents --invert-paths --force`
5. **Re-add the remote** — filter-repo drops it on purpose — then force-push all branches and tags.

Then the wrapper, and the registry offset that goes with it:

```bash
cd ~/Projects && mv isac isac-tmp && mkdir isac && mv isac-tmp isac/isac
mv ~/Projects/isac-ai-layer ~/Projects/isac/.agents
uv run --directory ~/Projects/drunken-team drunken-init --project isac --git-root isac
uv run --directory ~/Projects/drunken-team drunken-doctor --project isac
```

**Why the Boss runs all of it:** step 5 is a force-push, denied to an agent by
`.claude/settings.json` and by the DT-236 hook regardless of any Discord answer. Steps 1 and 3 touch
`.agents/`, which belongs to Antigravity. And the registry path moves under ISAC, so anything holding
`~/Projects/isac` as a repo path needs to know.

**Every commit SHA changes.** DT-248 quotes `103794d` and `bb80153` by name; it needs a comment
recording that those hashes no longer resolve, and why.

> Writing this section tripped the DT-236 hook twice — the deny scan reads a `git push --force` in
> *prose* as the command itself. Both times the fix was to write the instruction without the literal
> string on its own line, or to use `Write` rather than a shell heredoc. It errs toward a prompt,
> which is the direction chosen, but it is worth knowing before documenting a blocked command.

## 15. DT-251 — what the board can actually do (#103, in review)

`jira_mcp` had touched `/rest/agile/1.0` in exactly one place — a lookup asking whether a board
exists, for DT-234's warning. It never read what the board *is* and never asked what it can *do*.
`jira://board` is not the board either: it is a JQL search with `'To Do', 'In Progress', 'In Review'`
hardcoded, so a project whose columns are named otherwise gets nothing, silently. S4's shape again.

Surveyed live on 2026-08-16, before any code was written:

| board | project | type | backlog | sprints |
|---|---|---|---|---|
| 68 Drunken-Agy | DAGY | `kanban` | **no** | no |
| 71 DP board | DC | `simple` | yes, 5 issues | no |
| 72 DT board | DT | `simple` | yes | no |
| 105 TFH board | TFH | `simple` | yes | no |

**`type` does not predict capability**, which is what decided the design. The `kanban` board has no
backlog while the `simple` ones do, and a team-managed project can switch sprints on without its type
changing. So capability is *probed* — Jira answers in plain words, `Backlogs are not supported on
this board` — and type is only reported. **No board here supports sprints**, now established twice,
so a sprint branch would be code with no caller; the gap is one endpoint wide if that ever changes.

New: `BoardProfile` (cached once per process, and `board_warning()` now derives from it),
`JiraHTTPError` (keeps the status code `_make_request_sync` used to flatten away), and three tools —
`jira_board_info`, `jira_move_to_backlog`, `jira_move_to_board`. Both directions deliberately: a tool
that only moves work out of sight is a one-way door.

**Two things not to reverse.**

- **`POST /rest/agile/1.0/backlog/{boardId}/issue` takes any issue key from any project and moves
  it.** The board id constrains nothing, and one credential reaches DT, TWA and ISAC. Keys are
  checked against the server's own project *before* the call, compared whole rather than by prefix
  (`DTX-1` starts with `DT`), and one foreign key refuses the whole batch — a half-move that nothing
  recorded is the hardest state to reason back out of. S8 in a new place, same answer.
- **Backlog membership is not status**, and every result says so. A ticket parked in the backlog
  keeps the status it had. Read it as a status and board-versus-backlog becomes exactly the second
  disagreeing surface DT-250 removed.

Three states are kept apart in `BoardProfile` and must not be collapsed: *lookup failed*, *confirmed
no board*, and *board present, backlog question unanswered*. Folding the last into "no backlog"
would invent a limitation from a timeout and refuse work that would have succeeded.

Proven through real MCP stdio against live Jira: 10 tools listed, `ISAC-5` / `DTX-1` / a non-key /
51 keys each refused with a next step and never sent, and DT-251 moved to the backlog
(`backlog_total` 0 → 1) and back (1 → 0) with its status `In Progress` throughout. See §13's fourth
false negative for why the first run of that round trip looked broken.
