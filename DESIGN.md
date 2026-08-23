# Design

Why this repository is shaped the way it is.

**The rules themselves live elsewhere. This file holds the reasons.**
[`CLAUDE.md`](./CLAUDE.md) states how to work here, the skills state how to run a ticket and a
branch, `pyproject.toml` states what is pinned. Section 5 is the map. If you find a rule *stated in
full* in this file, that is a defect in this file — a second copy of a rule is the failure this
repository exists to cure, and a design document is not exempt.

What is recorded here instead: the decision, the failure that forced it, and the alternative
rejected. A rule whose reason is lost is a rule the next change deletes. Every claim below names the
ticket holding its evidence, because a reason without evidence is an opinion.

---

## 1. The problem

Two repositories held the same AI layer and drifted — 26 skills duplicated by name, `git-workflow`
at 73 lines against 196, while a merged PR told one copy to defer to the other. Nobody was wrong at
any single step, and two agents still ended up reading two different halves of one rulebook.

**One surface is the answer.** Where a second surface is unavoidable — Antigravity's tree, the
installed tool environment, `INDEX.md` — it is *generated from* the first, never maintained beside
it. Most of what follows is that sentence applied to a specific place.

---

## 2. Invariants

### 2.1 Nothing discovers a file by climbing the tree

`os.getcwd()` plus a loop over `os.path.dirname` is banned outright. Grep for the signature rather
than judging instances — it has been found three times in three shapes, and the third is why
case-by-case judgement is not good enough:

| where | what the climb actually decided | ticket |
|---|---|---|
| config loading | which credential was used | DG-254 |
| both Jira bridges | same, on the daemon's own path | DG-275 |
| `sync_customizations.py` | **where an install was written** | DG-276 |

The third was written off in the checkpoint as harmless — "it resolves a directory, not a secret".
The directory was a *write target*. Where skills and agents landed was decided by whichever
directory the shell happened to be in.

Two consequences. A destination comes from an argument or it does not come at all: there is no
default, because a sync that guesses is the failure and one that refuses costs a flag. And a guard
that greps for this signature must parse the **AST**, not the text — the guard and the guarded both
have to name the pattern in prose to explain the ban, and a substring search cannot tell an
explanation from a call. The first draft of the DG-276 guard failed on its own docstring.

> Precedence — env var, then registry, then the project's own `.agents/*.json` — and why a `.env`
> arrived disguised as rule one: `CLAUDE.md`, *Things that will bite you*.

### 2.2 A check whose failure is indistinguishable from its success is not a check

Jira answers a search made with a bad credential with `HTTP 200` and `{"issues": []}`. No exception,
no 4xx. A board holding 39 issues read as empty and every layer above believed it.

So liveness asks `/rest/api/3/myself`, which 401s. And a project key asks
`/rest/api/3/project/{key}`, which 404s — because a search scoped to a project that does not exist
*also* returns 200 and an empty page, byte-identical to a real but empty project (DG-260).

The generalisation is the point, and it has caught three different bugs: **ask an endpoint that
fails.** `drunken-doctor` printed `OK … (project ALPHA)` while Jira answered "No project could be
found with key 'ALPHA'", because the key was echoed back from the registry and never asked about.

### 2.3 Merge is not deploy, and deploy is not running

Three facts, and every surface has conflated two of them at some point. A merged PR does not update
`~/.local/share/uv/tools/drunken-guild/`, which is what the host launches. A reinstall does not
restart a running daemon. A ticket marked IN REVIEW is not merged code (DG-225).

The evidence, because this one keeps being treated as pedantry: `deployment.tool_env` checked that
seven modules were *present* — which a copy installed three months ago passes exactly as well as one
installed a minute ago. It reported green while the deployment was 22 files behind, and in that gap
sat DG-275's security fix, so the bridge the daemon runs was still reading a `.env` found by
climbing. Nothing on any surface said so. It now compares content (DG-278).

**Bytes, not timestamps.** `uv tool install` copies, so an mtime records when a file was written,
never which revision it holds.

### 2.4 A generated file that is also committed must be byte-identical everywhere

Whoever regenerates such a file decides what lands in git. Two independent things made that unstable
in the same week (DG-280, DG-271):

- **The environment leaked in.** The installers truncated with `cut -c1-N`, which counts *bytes*
  under `LC_ALL=C` and *characters* under a UTF-8 locale. Descriptions here are full of em-dashes at
  three bytes each, so one operator's install rewrote 13 lines of `INDEX.md` and the next
  regeneration reverted all 13. Both are "what the generator produces"; neither side is wrong, which
  is the worst shape a tracked artefact can have.
- **The commit hook disagreed with the generator.** `pre-commit` rewrote the freshly generated file
  — trailing whitespace, a blank last line. A generator whose output the commit hook edits *can
  never* produce the file that is in git.

The same disease, elsewhere: `requirements-dev.txt` recorded `uv pip compile` in its header while
`scripts/lock_deps.sh` regenerated it with `pip-compile`.

The rule: **one generator per artefact, deterministic across machines, emitting the exact form that
survives a commit.**

### 2.5 The rest, in one line each

These are stated in full where they are enforced. Here is only why they exist.

| invariant | why | stated in |
|---|---|---|
| Import-time failure is never a failure mode | a caller reads a message instead of watching an MCP server vanish; every error carries a remediation because "unknown project 'alpha'" only tells an agent to give up | `CLAUDE.md`, `src/core/errors.py` |
| An agent opens PRs, never merges; does not install; does not delete | the irreversible half of the work stays with a human. *Marking a thing unused beats removing it* — `requirements.txt` had drifted 113 lines with no reader and was retired with a note rather than deleted (DG-281) | `CLAUDE.md`, `skills/workflow/git-workflow/SKILL.md` |
| A bug's test is seen failing first | a test written after the fix proves only that it compiles | `CLAUDE.md` |
| The formatter is pinned exactly; `mypy` and `pytest` keep floors | a formatter has no right answer independent of its version, so a range gives one tree two answers (DG-265, DG-270); a new `mypy` finding something new is a result worth having | `pyproject.toml`, at the pin |

---

## 3. Decisions, and what was rejected

### 3.1 One repository, two deliverables

The runtime and the AI layer ship together. **Rejected:** keeping them separate, which produced §1.

**Cost accepted:** the Python gates cover `src/`, `tests/` and `scripts/` only — the AI layer is
markdown with no type checker, guarded by `scripts/check_doc_drift.py` and review. CI reads a "did
any non-markdown file change" job to tell the halves apart; the secret scan and doc-drift check are
ungated, because a secret pasted into a README is still a secret.

**One exception, deliberate:** DG-250 keeps a project's AI layer out of git. It does not apply here,
because here the AI layer *is* the product. `~/Projects/alpha-workspace` is the reference
implementation; this repository is the documented exception, not a defect to fix.

### 3.2 Jira is the only coordination surface

**Rejected:** a local board beside it, now retired to `_not_used/board-mcp/` (DG-250, DG-265).

**Cost accepted, stated rather than sold:** claim expiry is genuinely lost. A Jira assignee never
expires, so a ticket left assigned to an agent that died stays that way until a human looks. That is
a ten-second fix, weighed against a class of silent disagreement between two boards that costs
weeks.

> The lifecycle, and why the backlog is not a status: `skills/kanban/jira-tickets/SKILL.md`.

### 3.3 A ticket is scanned, not read — and leaves nothing to decide twice

The three-heading shape and the 120-word budget are in the skill. Two things learned since are not:

- **A ticket must not leave a choice open.** A SCOPE reading "an explicit argument *or* the script's
  own root" hands the decision to whoever picks it up, which is the deciding done twice. Decide
  before writing.
- **Record a change of mind on the ticket, not only in the PR.** DG-278 shipped as a `warn` where
  its SCOPE said `fail`; the reasoning belongs where the next reader of the ticket will look.

### 3.4 Ticket bodies carry structure, and the converter is symmetric

`to_adf()` turned every line into a paragraph, so tickets rendered as an undifferentiated wall —
including the three mandated headings, which arrived as ordinary sentences (DG-279).

`from_adf()` had to change with it: it rendered a heading as a bare line, so a ticket written with
structure was read back without it — the same wall by a longer route — and it walked a code block
rather than rendering it, turning a `# comment` inside a fence into a heading on the way back.

**Rejected:** a full Markdown parser. Four block shapes, no inline marks, no nesting — enough that a
ticket reads as a document, little enough that it cannot mangle a body nobody meant as Markdown.

### 3.5 Where a tool refuses rather than guesses

Three places make the same trade, and it is the house style rather than three coincidences:

- `drunken-usage` **does not know prices.** Rates are an operator input, and an unpriced model
  reports *no* cost rather than a smaller one. It also counts Claude only, and says so in every
  report rather than presenting a partial total as a whole one.
- The away-mode hook's allow list produces **no decision**, not `allow`. The hook never *widens*
  permission — and the deny list is checked first, so a 👍 cannot authorise `rm -rf`.
- A sync with no named destination **exits** (§2.1).

The shared shape: when a tool cannot know something, it says so. An under-reported cost and a
silently widened permission are both worse than a refusal.

> The full hook resolution order, and the two-layer split the model cannot see: `CLAUDE.md`,
> *Away mode*.

---

## 4. Deliberately absent

- **A second Jira surface.** Everything reaching Jira goes through `drunken-jira-mcp`.
- **A local board.** §3.2.
- **A second config emitter.** `install_mcp.sh` is a thin wrapper over `drunken-config`, which reads
  the registry, knows a repository's config from a host application's, and merges rather than
  overwrites. A second emitter would be two things answering one question.
- **Story points and priority.** A team-managed Jira project cannot set `priority` at all — every
  issue reads `Medium` because that is the only available value — and no story points exist. Urgency
  is expressed with labels. A constraint of the instance, not a gap to fill.
- **A `.env` anywhere in the loading path.** §2.1.

---

## 5. Where the rules live

| question | file |
|---|---|
| how to work in this repository | [`CLAUDE.md`](./CLAUDE.md) |
| where things stand right now | [`SESSION_CHECKPOINT.md`](./SESSION_CHECKPOINT.md) |
| how to write and run a ticket | `skills/kanban/jira-tickets/SKILL.md` |
| branch, commit, PR and merge rules | `skills/workflow/git-workflow/SKILL.md` |
| what each component does | [`Drunken-Guild-Guide.md`](./Drunken-Guild-Guide.md) |
| wiring the MCP servers into a project | [`Integration-Guide.md`](./Integration-Guide.md) |
| agent-facing rules for this repository | [`.agents/AGENTS.md`](./.agents/AGENTS.md) |
| what is pinned, and why | `pyproject.toml`, at each pin |
