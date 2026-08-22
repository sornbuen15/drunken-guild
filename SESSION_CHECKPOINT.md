# Session Checkpoint

Short-term memory between sessions. **Read this first; update it before ending your turn.**

Rule for this file, learned the hard way: **finished work does not live here.** It goes to the
release note, the Jira ticket, or `CLAUDE.md`, and this file links to it. The previous version reached
860 lines and 19 sections, several of which existed only to correct earlier sections — at which point
nobody reads it, and a handoff nobody reads is worse than none. See *What was cut* at the bottom.

Last updated: 2026-08-21 · **v2.3.0 released** · `develop` is where work lands

---

## 1. Start here

The last two rounds are merged, deployed and closed; all three projects read clean. What is
left is in §3, and it is mostly decisions rather than code.

DT-255's measurements are kept because they are the reason the tool surface looks the way it
does: a five-issue search cost **14,847 characters and now costs 894**, Discord's tool
descriptions went 4,127 → 1,260, and the Jira ones grew 2,665 → 3,432 on purpose — the
ticket rule and the field ids are paid once per session and returned by the first search.
Two things that fell out of it and are easy to re-learn the hard way: **priority cannot be
set on a team-managed project at all** (Jira's own `createmeta` says so, use `labels`), and
**there are no story points**, so capacity planning cannot work here.

## 2. Where things stand

**Do not type this section. Run it (DT-257):**

```bash
uv run drunken-status --project drunken-team          # add --tests for the real suite result
```

It reports `main`, `origin/develop`, where your branch sits against it, open PRs, and every
non-Done ticket with its assignee — from git, `gh` and Jira rather than from memory. Anything it
could not reach says so; an absent source is never rendered as an empty answer.

The typed table that used to live here went stale within an hour of being written, twice in both
directions, and was wrong again on the day it was replaced — naming three PRs as awaiting merge
that had all merged, beside a test count 49 behind. What stays hand-written below is what cannot
be derived: what was decided, and why.

### Rounds since v2.3.0, all merged and deployed

DT-254, DT-255, DT-228 (#112–#114), then DT-256, DT-257, DT-259 (#117–#119). Each round was
merged onto a throwaway integration branch first and ran clean. `drunken-doctor` reads
**27 ok, 0 warning, 0 failed** — the first time this project has had no standing warning.

The deployment was reinstalled on 2026-08-21 and matches: `deployment.mcp_pin` is 1.28.1,
`load_dotenv` is absent from the installed copy. **Merge is not deploy, and deploy is not
running** — a server process started before a reinstall holds the old code until it
restarts. Three separate facts; all three were wrong at some point in that round.

### ALPHA and BETA are usable now

Both are software projects with boards, and both were probed rather than assumed:

| | Jira | board | git |
|---|---|---|---|
| `alpha` | ALPHA | 141, backlog | `alpha-workspace/alpha` |
| `beta` | BETA | 140, backlog | `beta/beta/beta-backend` |

Discord is **one identity shared by all three**, not one channel per project (DT-247). The
bot authenticates and can read the channel — checked live, not read off a config.

Two things §6 and §3 used to warn about are no longer true: ALPHA's `.env` is untracked and
gitignored and nothing reads it since DT-254, and `alpha/scripts/` holds two unrelated
project scripts rather than a vendored copy of this tooling.

## 3. Open, and who owns it

**Boss — decisions**

- **Release 2.4.0.** Not 2.3.1: the round added two commands and changed tool contracts —
  `.env` is no longer read at all, `jira_search_issues` returns a different default shape,
  `jira_create_issue` no longer returns `self`. Strict semver would call those major; 3.0.0
  is reserved for removing the deprecated `request_boss_approval`, so 2.4.0 with the
  breaking changes stated plainly at the top of the note.
- **DT-260** — do it or close it. `drunken-doctor` verifies the credential (`/myself`) and
  never that the project key exists, so it printed `OK … (project ALPHA)` while Jira answered
  `No project could be found with key 'ALPHA'`. The immediate cause is fixed; the blind spot
  is not.
- Two local Docker images left behind on purpose (an agent does not delete):
  `docker rmi drunken-team:pinned drunken-team:unpinned`

**Agent, next**

- **DT-226** — still **do not open the transport**. §7 is unchanged: the DNS-rebinding
  finding and the missing inbound guard are both untouched.

**The agent layer — see `~/Projects/ai-team-toolkit/SESSION_CHECKPOINT.md`**

That repo authors the skills and agents installed into `~/.claude/`, and its checkpoint
carries the work: 12 of 30 global skills drive a kanban board that no project declares and
this project's `CLAUDE.md` forbids; agents have no index; its `CLAUDE.md` must become both
a catalog and the template other projects copy, covering this project's MCP servers. Its
sync script had been failing silently for two months and is fixed.

Nothing there is actionable from this repo. It is named here so the two do not drift.

**Antigravity** — ALPHA's `.agents/AGENTS.md` still tells it to run the vendored scripts.
Those instructions change before the scripts can be parked. This project's own `AGENTS.md`
was corrected in #119.

**Dropped on 2026-08-19, by the Boss:** BETA's project migration, DT-237, DT-248 and
DT-258. Do not re-raise them in a handoff.

## 4. Traps that are still live

1. **The installed tool env is a separate deployment.** `~/.local/bin/drunken-*` symlinks into
   `~/.local/share/uv/tools/drunken-team/`, and that is what a host config launches — not this
   checkout. Merging does not deploy. `drunken-doctor` now reports the gap (DT-252); believe it over
   any assumption. Reinstalled from `04f29f5` on 2026-08-17.
2. **`uv tool install` ignores `uv.lock`.** Closed end to end: `drunken-config --kind install`
   writes the pinned requirements and prints the command, and the deployment now reports
   `deployment.mcp_pin` 1.28.1 matching the lock. Proved by building the image both ways — with
   the flag 1.28.1, without it 1.29.0. **The command only prints; it installs nothing.** That
   distinction cost a round: the deploy silently did not happen and every surface looked fine.
3. **A Jira search cannot tell you a project exists.** `ALPHA` was renamed and our registry kept
   the dead key; searches returned HTTP 200 with an empty list and `drunken-doctor` printed
   `OK … (project ALPHA)`, because it verifies the credential and never the project. Both are
   fixed, the blind spot is DT-260. BETA's `git_root` warning is also gone — it was pointing two
   levels too shallow, which is what the warning had been saying all along.
4. **A finding closed in one module is not closed in the codebase.** S3 was written up as closed by
   DT-224 and was still alive in `service/discord_utils.py` — fixed in #112, and the signature
   (`os.getcwd()` plus a loop over `os.path.dirname`) is now absent from `src/`. The lesson stands:
   grep for the pattern, do not reason about it.
5. **`.gitignore` can silently drop source from a commit.** `*token*` swallowed a whole test file on
   2026-08-19: `git add -A` skipped it, the commit succeeded, pre-commit passed, and the local suite
   stayed green because the file was on disk. A PR shipped claiming 21 tests it did not contain.
   Nothing in the pipeline could contradict it.

## 5. Six ways running it can lie to you

Every real defect in this project has been found by running something and looking — never by the
suite. But the harness has its own failure modes, and all six of these under-reported success rather
than over-reporting it:

1. `drunken-doctor`'s `0 failed` summary line was counted *as* a failure by a grep reading it.
2. `uv run --directory X` overrides a preceding `cd`, so three projects were probed from one.
3. **zsh does not word-split an unquoted parameter** — `$args` holding `--project drunken-team`
   arrives as one argv entry, argparse ignores it, and a security boundary looks broken when it is not.
4. **The agile API's reads lag its writes**, and `GET /board/{id}/issue` on a team-managed board
   returns backlog issues too — so it is not a membership test.
5. An S2 probe printed `SERVED` on all three rows because it called a tool that does not exist and
   then tested for the word "error", which is absent from `Unknown tool`. **This nearly became a
   security report.**
6. A test asserted `not report.failed` over a whole doctor report — clean only on a machine that has
   a registry. CI has none, `develop` went red.

**Read what the thing actually said. Do not grep for a word you expect to be absent.**

## 6. BETA — the survey that has to survive

The application source **was never in `sornbuen15/beta`**. On the remote, `beta-backend` is a
dangling gitlink — mode `160000`, commit `69c85d9`, and no `.gitmodules` anywhere. The 77 commits
there are the *wrapper*: `.agents/`, `scripts/`, `k8s/`, `Makefile`.

| where | what | history |
|---|---|---|
| `sornbuen15/beta` | wrapper + AI layer + dangling gitlink | 77 commits, carries the inert token |
| `~/Projects/new-beta-parked/beta-backend` | **the application** | 67 commits, HEAD `69c85d9`, working tree emptied |
| `~/Projects/beta/beta/beta-backend` | the application, flattened | 1 commit, no remote |
| `~/.gemini/history/beta` | Antigravity's. **Do not touch** | — |

The last two are the same thing split in half: checking out `69c85d9` from the parked repository
produces 122 files **byte-identical** to the rebuild; the rebuild's only extras are 11 `k8s`
manifests from the wrapper. **Nothing is lost.**

A `git filter-repo` removing `.agents` was run against a throwaway mirror and verified: 77 → 70
commits, 4 branches intact, `.agents` gone from every commit, token string absent, 27 source files
preserved. Whether to publish that, or to make the application repo the one that matters, is open —
and merging the two repos would settle the token question for free, since the wrapper would stop
being a repository at all.

## 7. DT-226 — reviewed, not approved

**Recommendation: do not open the transport yet**, and not because of anything S1/S2/S8 left behind.
`mcp` 1.29's `FastMCP` enables DNS-rebinding protection **only when the host is loopback**:

```python
if transport_security is None and host in ("127.0.0.1", "localhost", "::1"):
```

So setting `--host 0.0.0.0` to satisfy Boss's rule 3 silently switches it off — protection absent
exactly where it is needed. S6's lesson in a new place: *safe by accident is not safe by
construction.* If it proceeds, pass `TransportSecuritySettings` explicitly and test that a
non-loopback host still gets it.

Also missing first: there is no inbound guard (`core/http.py` covers outbound only; `AuthError` and
`AuthzError` have been reserved and unused since 2.1.0), and DT-228 should land so manifests are
generated rather than hand-written.

## 8. What was cut, and where it lives now

Nothing was lost. If you are looking for something that used to be here:

| Was | Now |
|---|---|
| §4 Delivered, §5 S1–S12, §12 numbers, §15 DT-251, §16 DT-95, §18 acceptance run | The **v2.3.0 release note** on GitHub |
| §6 e2e / S12, §7 CI, §8 principles, §11 working agreements | **`CLAUDE.md`** |
| §14 BETA's five-step plan | Superseded by §6 above — the old steps would fail against what is on disk |
| §3 locked decisions | `CLAUDE.md`, except the **Git-in-MCP** entry, which pointed at a "§9.1" that never existed in this file. It was never built. Re-decide it with the conditions written down, or drop it |
| Post-mortems | Their Jira tickets — DT-248, DT-253, DT-254 |
