# Session Checkpoint

Short-term memory and context handoff between AI coding sessions.
**Read this at the start of a session and update it before ending your turn.**

Last updated: 2026-08-12 · version **2.2.0** on `develop` · Phase 2 of 6 complete

---

## 1. Where things stand

**Active work: "MCP Hardening & Portability"** — shipped as incremental 2.x releases.
Goal: any AI, any tool, running from any directory (including Docker/K8s/cloud) can use the MCP
servers safely, with no project ever holding a credential.

| | |
|---|---|
| Branch | `develop` — everything below is merged and green there |
| Merged | DT-189 (2.1.0) · DT-224 (2.2.0) · DT-232 · DT-233 · DT-234 · DT-235 |
| **Next** | **DT-225 — Phase 3 security hardening. It is not done. See §5.** |
| Jira | 7 tickets open. DT-225 blocks DT-226 and DT-236 |
| CI | 🟢 4/4 on `develop` |

> **⚠️ Read §5 before picking anything up.** DT-225 spent weeks marked IN REVIEW while none of it
> was ever merged, and a copy of this file on `feature/DT-225-security-hardening` still claims the
> security work is finished and that Phase 4 is safe to open. Both are false of `develop`. That
> branch is now 642 lines behind and **must not be merged** — it would revert DT-232/233/234.

**Full handoff, including everything Antigravity needs, is §14 of
`~/Projects/todo/drunken-team/MCP-ARCHITECTURE.md`.** That document is the cross-AI channel and is
the authoritative record; this file is the short version.

> **Do not call this work "v3".** Boss ruled (architecture doc §12) that it is bugfix + additive
> throughout. `3.0.0` is reserved for when things are *removed* (`--workspace`, the old socket path,
> the mcp 1.x SDK), not when they are added.

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

## 5. Findings — S1 to S12

**Fixed in 2.1.0:** S4 (Jira 200 + `[]` on a bad token), S5 (`__file__`-derived paths), S9 (version
drift), S10 (inverted `\n` escaping), S11 (`drunken-register` unusable and writes plaintext tokens
into the project), S12 (e2e tests writing to live Jira), 3 aiohttp CVEs, 3 bandit MEDIUM.

**Fixed in 2.2.0 (DT-224):** S3 (`.env` parent-walk deleted with `jira_mcp/config.py`), S11.

**Still open on `develop` — all of Phase 3 / DT-225.** Re-verified against `origin/develop` on
2026-08-12, file by file. None of this is theoretical:

| # | State on `develop` today |
|---|---|
| S1 | `query_project_context` does `if os.path.isabs(file_path): resolved = file_path` — no containment check of any kind. Arbitrary file read |
| S2 | No authorization check anywhere in `board_mcp/server.py` — `project` is a lookup key, not a boundary |
| S6 | No `chmod` on the daemon socket |
| S8 | `jira_search_issues` passes raw JQL straight through; `--project` is not a security boundary |

> **⚠️ HTTP transport (Phase 4 / DT-226) must not open until S1/S2/S8 are fixed.** Everything is
> local stdio today, which is the only reason these are not remotely reachable — and Phase 4 is
> precisely what would change that. DT-225 is linked as blocking DT-226 and DT-236 in Jira.

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
| **2.3.0** | ⛔ **DT-225 — security hardening, S1/S2/S6/S8. Not started on `develop`.** Redo on a branch cut from current `develop`, cherry-picking `71fddb8`; **do not merge the old branch** |
| **2.4.0** | DT-226 — dual transport + pluggable bearer auth. **Blocked by DT-225** |
| **2.5.0** | Discord daemon multi-tenant. **Needs a deprecated socket-path fallback**, else it is breaking (§12.3) |
| **2.6.0** | Config generator: `.mcp.json` + antigravity `mcp_config.json` + docker/k8s manifests |
| **3.0.0** | Removals only: drop `--workspace`, drop the old socket fallback, migrate to the mcp 2.x SDK |

## 10. Outstanding debt

1. **`main` is 7 commits behind `develop`** and has 7 it does not — nothing since 2.1.0 has been
   released. This is a release decision, not drift. *(The old entry here said local `main` had
   diverged from `origin/main` by 20 files. It has not: both are `3d18c2e`, 0 ahead, 0 behind.
   DT-230 closed as stale.)*
2. **24 bandit LOW findings** — mostly `try/except/pass` in `service/`. Not gated, not hidden.
3. **`uv tool install` ignores `uv.lock`** — the tool env has mcp 1.29.0 while the lock pins 1.28.1.
   Both satisfy `<2`, but drift inside the range is still possible. Phase 6's generator should emit
   `--with-requirements`.
4. **`.claude/settings.json` denylist is not yet enforced by anything but the harness.** DT-236 gives
   it teeth; until then it is policy, not a control.

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

Measured on `develop` @ `5a1925d`, 2026-08-12:

```
431 tests passed (2 deselected)   ·   Python 3.10 and 3.13
ruff check / ruff format / mypy --strict          clean
bandit -ll / pip-audit --strict / gitleaks        clean
scripts/verify_clean_install.sh                   22/22
CI on PRs #76 #77 #78 #80 #81                     4/4 green each
```

Two things were proven against **live Jira** rather than argued:

- **S4** — the same bad token yields `FAIL 401` with remediation from `verify_jira_identity`, where
  `jira_search_issues` still returns `[]` with HTTP 200.
- **DT-234** — DT, TFH and DC stay silent; TWA and ISAC warn. While checking, every board on the
  site was surveyed: **none supports sprints**, and for DT the agile backlog is a strict subset of
  the board (backlog-only = 0), so nothing is stranded in a backlog. No sprint support is needed
  anywhere, which is why DT-234 deliberately does not implement any.
