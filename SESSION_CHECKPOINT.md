# Session Checkpoint

Short-term memory and context handoff between AI coding sessions.
**Read this at the start of a session and update it before ending your turn.**

Last updated: 2026-08-06 · version **2.1.0** · Phase 1 of 6 complete

---

## 1. Where things stand

**Active work: "MCP Hardening & Portability"** — shipped as incremental 2.x releases.
Goal: any AI, any tool, running from any directory (including Docker/K8s/cloud) can use the MCP
servers safely, with no project ever holding a credential.

| | |
|---|---|
| PR | [#74](https://github.com/sornbuen15/drunken-team/pull/74) → `develop` · **draft** · `MERGEABLE` |
| Branch | `feature/DT-189-core-foundation-dev` |
| Jira | DT-189 · **IN REVIEW** |
| CI | 🟢 **all 4 jobs green — first time since 2026-06-25** |

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

## 4. Delivered in 2.1.0

Eight new modules under `src/core/`. **The three MCP servers are deliberately not rewired yet** —
that is Phase 2 — so this is revertable on its own.

`paths` (`$DRUNKEN_HOME`, nothing from `__file__`) · `secrets` (pluggable `env:// file:// op://
keyring://`, resolved once per process, scheme-less references rejected) · `redact` (masked `Secret`,
base64-aware redactor) · `errors` (`DrunkenError` with remediation, `as_tool_result`) · `registry` v2
(in-memory v1 upgrade, optional `path`, validated ids) · `context` (`verify_jira_identity`) · `http`
(scheme-guarded `urlopen`) · `doctor` (`drunken-doctor`) · `init` (`drunken-init`)

## 5. Findings — S1 to S12

**Fixed in 2.1.0:** S4 (Jira 200 + `[]` on a bad token), S5 (`__file__`-derived paths), S9 (version
drift), S10 (inverted `\n` escaping), S11 (`drunken-register` unusable and writes plaintext tokens
into the project), S12 (e2e tests writing to live Jira), 3 aiohttp CVEs, 3 bandit MEDIUM.

**Open by design — Phase 3 / 2.3.0:**

| # | Issue |
|---|---|
| S1 | `board.py:578-609` `query_project_context` takes absolute paths, no `..` guard → arbitrary file read |
| S2 | `board_mcp` tools: `project` has no authorization |
| S3 | `.env` parent-walk in `jira_mcp/config.py` + `discord_utils.py` → Phase 2 removes it |
| S6 | Unix socket has no permission set |
| S8 | `jira_search_issues` takes **raw JQL** → `--project` is not a security boundary at all |

> **⚠️ HTTP transport (Phase 4) must not open until S1/S2/S8 are fixed.** Today everything is local
> stdio, so none of these are remotely reachable.

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

**~55 junk tickets are still there.** Awaiting Boss's decision — Claude does not delete data.

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
| **2.2.0** | `--workspace` → `--project` across all three servers; delete the `.env` parent-walk (S3); wire `ProjectContext` into the servers; retire `drunken-register` (S11) |
| **2.3.0** | Security hardening — S1, S2, S8, S6. **Must land before 2.4.0** |
| **2.4.0** | Dual transport + pluggable bearer auth |
| **2.5.0** | Discord daemon multi-tenant. **Needs a deprecated socket-path fallback**, else it is breaking (§12.3) |
| **2.6.0** | Config generator: `.mcp.json` + antigravity `mcp_config.json` + docker/k8s manifests |
| **3.0.0** | Removals only: drop `--workspace`, drop the old socket fallback, migrate to the mcp 2.x SDK |

## 10. Outstanding debt (none of it blocks the merge)

1. **Local `main` has diverged from `origin/main`** — 20 files differ (`not_use/` and this file are
   still tracked on the remote but absent from local `main`). The PR branch was rebased onto
   `origin/develop` to avoid carrying those deletions into the PR. **Unresolved; needs Boss's call.**
2. **24 bandit LOW findings** — mostly `try/except/pass` in `service/` and in `jira_mcp/config.py`,
   which Phase 2 deletes anyway. Not gated, but not hidden either.
3. **`uv tool install` ignores `uv.lock`** — the tool env currently has mcp 1.29.0 while the lock pins
   1.28.1. Both satisfy `<2`, but drift inside the range is still possible. Phase 6's generator should
   emit `--with-requirements`.
4. **~55 junk `[E2E TEST]` tickets** in DT (see §6).

## 11. Working agreements

- Jira is SSOT: `TODO` → `IN PROGRESS` → `IN REVIEW` → `DONE`. **Never skip IN REVIEW.**
- One Jira ticket per phase; each phase merges independently without breaking the one before it.
- A test for a security finding must be **seen failing first**, to prove it has teeth.
- Never put absolute paths in another project's `.mcp.json` — it leaks into git.
- No identity, token, or secret may ever enter a commit.
- **Do not touch or archive `.agents/` files or `~/.gemini/antigravity-cli/brain/*/worktrees/`.**
- Antigravity does **not** edit `drunken-team` source during this work — a merge conflict inside a
  security boundary is the easiest way for a hole to slip through.

## 12. Verified numbers

```
402 tests passed (2 deselected)   ·   Python 3.10 and 3.13
ruff check / ruff format / mypy --strict          clean
pip-audit --strict / bandit -ll / gitleaks (116 commits)   clean
scripts/verify_clean_install.sh                   22/22
CI on PR #74                                      4/4 green
```

S4 was proven against **live Jira**: the same bad token yields `FAIL 401` with remediation from
`verify_jira_identity`, where `jira_search_issues` still returns `[]` with HTTP 200.
