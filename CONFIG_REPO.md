# The config repo

What REQ-020 (`.ai/PRD.md`) names and does not yet build: the one place a project's AI layer comes
from. REQ-019 and REQ-020, and the Layering context in `.ai/DOMAIN.md`, are the source of every
term this page uses — read those first if a word here is unfamiliar.

**This page defines the layout. It builds nothing.** The `.git/info/exclude` writer (DG-440) and
init's copy-in (DG-441) are later Tasks, hung from this Task's Story (DG-436) — along with init no
longer writing a tracked `AGENTS.md`/`CLAUDE.md` into a project (DG-442), init setting up the hooks
and Jira configuration (DG-443), and the matching README/getting-started update (DG-444). Nothing
here is built on the result of Spike DG-432 yet — that spike is about whether Claude Code loads a
`.claude/settings.json` reached through `.git/info/exclude` at all, and this page's layout does not
depend on its answer.

---

## What it is

One private GitHub repository. Not one repository per project — REQ-020 decided that: files are
copied into a project's folder, not symlinked, so a config repo holding many projects is the same
shape as holding one.

Inside it, **one folder per project, named with that project's registered id** — the same id the
project's own Jira and `drunken-doctor --project` already use. This page never names a real one;
every example below uses the placeholder `example-project/`.

```
config-repo/
  example-project/
    AGENTS.md
    CLAUDE.md
    .claude/
      settings.json
      hooks/
    hook-config.*
    jira-config.*
  another-example/
    ...
```

The exact filenames under `.claude/` and the hook/Jira configuration's own format are for DG-440
and DG-441 to decide when they build the exclude writer and the copy-in; this page fixes only what
kind of file the folder may hold, not every name in it.

---

## What a project's folder may hold

Everything REQ-019 calls a project's AI layer — instructions about how the AI works on the
project, never facts about what the project builds:

- `AGENTS.md` — the instruction file.
- `CLAUDE.md` — the one-line `@AGENTS.md` adapter (REQ-015).
- `.claude/` — settings and hook entries.
- The hook configuration.
- The Jira configuration (board, project key, field ids — not a credential; see below).
- Any other agent's own instruction file (a `GEMINI.md`, for instance), on the same terms.

**This list is provisional.** The canonical list of paths that make up a project's AI layer is the
AI-layer list module DG-437 adds in `src/core` — once that merges, this page points at it instead
of restating it, so the two cannot drift apart. The agreement test for that belongs with DG-437, or
the Task that consumes it (DG-438), or a follow-up ticket — not this one.

Facts about the work — requirements, the domain, the stack, what is built — stay in the project's
own repository (`.ai/PRD.md`, `.ai/DOMAIN.md`, its README), never here. A config repo folder that
drifts into holding those has recreated the second surface REQ-019 exists to prevent.

---

## What must never be in it

**No secret, no token, no personal data.** A private repository is not an exemption — `CLAUDE.md`
in this very repository already says a reference without a scheme is an error, not a literal, and
that rule holds here too: `env://…` or `file://…#key`, never a token, channel id, workspace URL or
account email inline.

**Where Jira credentials live is an open PRD question (`.ai/PRD.md`, Open — for /clarify, REQ-020)
and is not decided by this page.** The Jira *configuration* — board id, project key, the field ids
`jira_board_info` reports — may live in a project's folder, because none of that is a secret; the
credential itself is a separate, still-open question and nothing here answers it.

---

## The exception

This repository is exempt (REQ-006, REQ-019's own **Decided** line): here the AI layer — `skills/`,
`agents/`, `AGENTS.md`, `CLAUDE.md` — *is* the product, so it stays tracked in this repo's own git,
not in the config repo.

---

## Not built yet

- **Nothing writes `.git/info/exclude` yet.** Hiding the copied files from the project's own git is
  DG-440.
- **Init does not copy anything in yet.** The copy step, from the config repo into a project's
  folder, is DG-441.
- **The AI-layer list this page's "may hold" section restates by hand is not yet a module.**
  DG-437 adds it in `src/core`; see above.
- **Nothing here is built on DG-432's result.** That spike checks whether Claude Code reads a
  `.claude/settings.json` reached only through `.git/info/exclude`; until a recorded run answers
  that, this layout is a definition, not a working pipeline.
