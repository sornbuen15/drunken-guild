# The config repo

What REQ-020 (`.ai/PRD.md`) names and does not yet build: the one place a project's AI layer comes
from. REQ-019 and REQ-020, and the Layering context in `.ai/DOMAIN.md`, are the source of every
term this page uses — read those first if a word here is unfamiliar.

**This page defines the layout.** The `.git/info/exclude` writer (DG-440) and init's copy-in
(DG-441) are built — see "What is built" below. Still ahead, as later Tasks of Story DG-436 (this
Jira parents them to the Epic DG-434, not to the Story): init no longer writing a tracked
`AGENTS.md`/`CLAUDE.md` into a project (DG-442), init setting up the hooks and Jira configuration
(DG-443), and the matching README/getting-started update (DG-444). Spike DG-432 found that a
git-excluded `CLAUDE.md`/`.claude/settings.json` loads in Claude Code exactly like a tracked one
(see "What is built"); DG-443's interactive trust-prompt question is still open.

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

The exact filenames under `.claude/` and the hook/Jira configuration's own format are for DG-443 to
decide, when it builds hooks and Jira configuration; this page fixes only what kind of file the
folder may hold, not every name in it.

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

## What is built

- **`.git/info/exclude` writer (DG-440, `src/core/exclude.py`).** `exclude_ai_layer()` appends the
  one AI-layer list's patterns, between markers, idempotently — in a plain clone and in a `git
  worktree` alike. It refuses a `repo_root` that git itself does not resolve to its own top level,
  which is why `drunken-init`'s copy-in (below) calls it with the git root, never a nested project
  path.
- **`drunken-init --config-repo` copy-in (DG-441, `src/core/layer_copy.py`).** Takes the path to a
  *local* clone of the config repo (the Boss clones it; nothing here does) and the project's
  registered id, copies only the files `core.ai_layer` lists from that project's config-repo folder
  into its registered path, then calls the exclude writer so `git status` stays clean. Copies, never
  symlinks — never through a destination that is itself a symlink either, and never by following one
  inside the config repo's own project folder. Checked by *path*, not by whether the destination
  currently exists: a path the project's own git already tracks — **in the index with real content,
  or present in `HEAD`** — aborts the whole call, naming it, before anything is written, whether or
  not it is still present on disk (a committed file deleted from the working tree, or taken out of
  the index alone by `git rm --cached` while staying in `HEAD`, is still tracked; an intent-to-add
  placeholder for a never-committed path is deliberately not). The tracked check goes through
  `core.exclude.run_git` — the one git caller with **every** `GIT_*` environment variable stripped
  (a fixed three-name list was tried first and missed `GIT_INDEX_FILE`, which redirects what the
  index check answers without redirecting which repository resolves at all) — and fails closed on
  anything git does not answer with one of its own documented exit codes. The exclude entries are
  written **before** any file is copied, not after, so a failure there (a corrupted marker block)
  leaves the project tree exactly as it was rather than copied-but-untracked; a real I/O failure
  partway through the copy itself names every file already copied, and re-running after fixing the
  underlying problem is idempotent. An existing *untracked* file that differs from the config repo is
  skipped, named on stderr, and fails the run (`exit 1`) unless `--overwrite-ai-layer` is passed;
  identical is "unchanged" and stays green. Works for a project registered at a subfolder of a larger
  repository too: `--git-root` is a plain relative offset, either direction — `".."`/`"../.."`
  ascends to the real top level when `--path` is itself nested inside it, the same field ALPHA's
  descending case already used (`core.context.ProjectContext.git_root_path`). `core/doctor.py` still
  runs its own, separate, **read-only** `git ls-files` for an unrelated check (`tracked_ai_layer_paths`)
  — not routed through `run_git` yet; a read-only check never writes, so it is out of this ticket's
  scope, left for a follow-up. Still open: DG-442 (init stops writing a tracked
  `AGENTS.md`/`CLAUDE.md` from the packaged template — until then the two can collide on the same
  files in one run, which is exactly the case the non-zero exit above exists to surface rather than
  bury), DG-443 (hooks and Jira configuration — blocked on where a credential lives) and DG-446
  (migrating an already-tracked project).

## Not built yet

- **The AI-layer list this page's "may hold" section restates by hand is not yet reflected
  everywhere it could be.** `core.ai_layer` (DG-437) is the canonical module both DG-440 and DG-441
  read; this page still names it by hand rather than generating from it.
- **Nothing here is built on DG-432's result beyond what it already answered.** The spike (comment
  on DG-441) found a git-excluded `CLAUDE.md`, `AGENTS.md`, a settings.json hook and a path-scoped
  rule load in Claude Code exactly like tracked ones, under `claude -p`; the interactive trust-prompt
  case for hooks is still open (DG-443), not answered by this layout.
- **Init does not yet set up hooks or Jira configuration.** That is DG-443.
- **Nothing migrates an already-tracked project's AI layer out of its repository.** That is DG-446.
