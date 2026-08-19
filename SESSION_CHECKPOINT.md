# Session Checkpoint

Short-term memory between sessions. **Read this first; update it before ending your turn.**

Rule for this file, learned the hard way: **finished work does not live here.** It goes to the
release note, the Jira ticket, or `CLAUDE.md`, and this file links to it. The previous version reached
860 lines and 19 sections, several of which existed only to correct earlier sections — at which point
nobody reads it, and a handoff nobody reads is worse than none. See *What was cut* at the bottom.

Last updated: 2026-08-19 · **v2.3.0 released** · `develop` is where work lands

---

## 1. Start here — the token-economy round (DT-255)

Every number below was **measured on 2026-08-17**. Re-measure after the work and record the real
figures; a claimed saving is exactly the sort of thing this file exists to distrust.

```
jira_search_issues, 6 issues     5,697 tokens   ← 95% of it raw ADF description
  the same search without it        296 tokens
discord, 3 tool descriptions     1,033 tokens   ← 410 for the DEPRECATED blocking tool
tickets written in one session   3,079 for 5 — the longest 803 words
  the project's own older tickets     49 words
```

`minify_issues` is a promise the function does not keep: it returns Atlassian Document Format
verbatim, and ADF wraps one sentence in roughly four times its length.

| | Work | Effect |
|---|---|---|
| **A1** | `jira_search_issues` → default `brief`, no description | −90% per search |
| **A2** | ADF → plain text when the full issue *is* requested | −3–4× on the remainder |
| **A3** | brief returns `parent` + `parent_summary` | removes 2–3 follow-up calls |
| **A4** | `create_issue` returns the key, not the `self` URL | free |
| **B1** | `create_issue` accepts `parent` | without it an Epic has no children, Timeline is empty |
| **B2** | `duedate` + Start date | the "what is available when" question |
| **B3** | `labels` | **stands in for priority**, which team-managed projects lack |
| **B4** | `board_info` reports issue types and settable field ids | stops anyone hardcoding a custom field |
| **C1** | Ticket rule in the `create_issue` docstring | +57 tokens, returns ~700 per ticket, **every AI sees it** |
| **C2** | Warn when long **and** parentless — never reject | DT-234's mechanism, already proven |
| **D** | Discord: shrink the deprecated tool, drop `Args:`/`Returns:` the schema already carries | 1,033 → ~300 |

**Also add to DT-255:** the *state* half of this file — branch, tests, PRs, tickets — should be read
from git, Jira and CI rather than typed. It went stale within an hour of being written, which is the
evidence that the idea is necessary rather than over-engineering.

### Established while working this out, none of it obvious

- **`priority` cannot be set on a team-managed project at all.** That is why every DT ticket reads
  `Medium`, and why the surviving `/refine` — which promotes issues labelled `Critical` — could never
  have done anything here. Use `labels` or `Rank`.
- **`parent`, `duedate` and Start date already exist on DT.** Jira is ready; our payload sends four
  fields and stops. Start date is `customfield_10015` *on this instance* — resolve it at runtime.
- **No story points field**, so Capacity cannot work. Not a gap to fill.
- **`board_mcp` is declared in no `.mcp.json`.** Keep it that way: 2,162 tokens per request for a
  retired server.
- Context belongs on the Epic or Story and should be **linked, not copied**.

## 2. Where things stand

| | |
|---|---|
| `main` | `d8b81c9` — **v2.3.0 released** 2026-08-17 |
| `develop` | `edcb575`, **670 tests green** |
| Open PRs | **#112 DT-254** · **#113 DT-255** · **#114 DT-228** — all awaiting the Boss's merge |
| Jira | **To Do:** DT-226 · DT-237 · DT-248 · DT-256 · DT-257 · DT-258 · **In Review:** DT-228 · DT-254 · DT-255 · **Done:** DT-252 |

Verify these three before trusting the table: `origin/develop`, the PR states, and Jira. This section
has been wrong twice, in both directions — and DT-257 exists to stop it being typed at all.

### The round of 2026-08-19, integration-tested together

The three PRs were merged onto a throwaway `integration/round-254-255-228` branch before being
handed over. **No conflicts**, and on the combined tree: 708 tests green, `drunken-doctor` 24 ok /
2 warning / 0 failed, `verify_clean_install.sh` 22/22. Merge them in any order.

Measured on the merged tree, from a directory unrelated to any project:

```
DT-254  project_root()   /Users/r.jakkawan/Projects/drunken-team   (via the registry, no walk)
        DISCORD_* leaked into os.environ: none
DT-255  a 7-issue search 1,294 chars      — the old shape cost 14,847 for five
DT-228  servers declared ('drunken-jira-mcp', 'drunken-discord-mcp')   board: absent
```

## 3. Open, and who owns it

**Boss**

- **Merge #112, #113, #114.** Integration-tested together, see §2.
- **BETA** — create a new **Software / Kanban** project, then move the 3 open issues (BETA-3, BETA-4,
  BETA-132). DT-237's stated cost of 170 issues is **wrong**: ALPHA has 0 open, BETA has 3. Fix that
  ticket. Requirements memo is **BETA-132**.
- **DT-248** — nothing left to do; close it.
- **DT-237** — decide. "Do nothing" stopped being the right answer once the plan became to work on
  BETA and ALPHA.
- **DT-258** — three options in the ticket; option 2 is the one that generalises. Narrowing a
  credential exclusion is not a call to make inside another ticket.
- Two local Docker images left behind on purpose (an agent does not delete):
  `docker rmi drunken-team:pinned drunken-team:unpinned`

**Agent, next**

- **DT-256** — pyproject says 2.1.0 while v2.3.0 is tagged. Small, and it defeats DT-252's whole
  point: comparing checkout against deployment gives 2.1.0 on both.
- **DT-257** — derive this file's §2 from git, Jira and CI instead of typing it.
- **DT-258** — see above; needs the Boss's choice first.
- **DT-226** — still **do not open the transport**. §7 is unchanged, and DT-228 landing does not
  change it: the DNS-rebinding finding and the missing inbound guard are both untouched.

**Antigravity** — ALPHA's `.agents/AGENTS.md` still tells it to run the vendored scripts. Those
instructions change before the scripts can be parked.

## 4. Traps that are still live

1. **The installed tool env is a separate deployment.** `~/.local/bin/drunken-*` symlinks into
   `~/.local/share/uv/tools/drunken-team/`, and that is what a host config launches — not this
   checkout. Merging does not deploy. `drunken-doctor` now reports the gap (DT-252); believe it over
   any assumption. Reinstalled from `04f29f5` on 2026-08-17.
2. **`uv tool install` ignores `uv.lock`** — the deployment has mcp 1.29.0 while the lock pins
   1.28.1. Reported by `deployment.mcp_pin`. **Fix is in #114, not yet merged and not yet deployed:**
   `drunken-config --kind install` writes the pinned requirements and prints the command. Proved by
   building the image both ways — with the flag it reports 1.28.1, without it 1.29.0.
3. **BETA's registry `git_root` points at a directory that is not a repository.** The warning is
   correct and **must not be silenced** until the repo question is settled — a green check would hide
   the divergence rather than close it.
4. **A finding closed in one module is not closed in the codebase.** S3 was written up as closed by
   DT-224 and was still alive in `service/discord_utils.py` — fixed in #112, and the signature
   (`os.getcwd()` plus a loop over `os.path.dirname`) is now absent from `src/`. The lesson stands:
   grep for the pattern, do not reason about it.
5. **`.gitignore` can silently drop source from a commit.** `*token*` swallowed a whole test file on
   2026-08-19: `git add -A` skipped it, the commit succeeded, pre-commit passed, and the local suite
   stayed green because the file was on disk. A PR shipped claiming 21 tests it did not contain.
   Nothing in the pipeline could contradict it. DT-258.

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
