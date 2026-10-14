# Repository Map

Moved out of README.md by DG-517 so README stays short. The tables below are unchanged — this is
the same content at a new address, still checked mechanically by
[`tests/test_readme_file_map.py`](./tests/test_readme_file_map.py) and
[`tests/test_readme_templates_inventory.py`](./tests/test_readme_templates_inventory.py).

## Repository map

Which directory is whose, verified against the tree rather than reasoned from memory. Each row
points at the file that owns the actual rule — this table says who touches the path and what
checks it, not what it says.

| path | for whom | hand-edited | generated / checked by |
|---|---|---|---|
| `.ai/` | this repository's own project documents — `PRD.md`, `DOMAIN.md` | yes | `scripts/check_doc_drift.py` scans it like any other doc |
| `AGENTS.md` | agents and contributors working *in* this repo | yes | `tests/test_agents_md.py` — the guild block exists, routes every situation, and stays byte-identical to `src/core/templates/AGENTS.md`'s block (DG-407) |
| `CLAUDE.md` | Claude Code specifically, as the `@AGENTS.md` adapter (REQ-015) | yes, but it must stay exactly that one line | `tests/test_agents_md.py::test_claude_md_holds_no_rule_agents_md_lacks` |
| `skills/` | AI agents — installed to `~/.claude/skills/` | yes, each `SKILL.md` by hand | `skills/INDEX.md` inside it is generated, not hand-edited — `scripts/install/install_skills.sh --index-only`; checked by `tests/test_install_index_determinism.py` |
| `agents/` | AI agents — installed to `~/.claude/agents/` | yes, each role file by hand | `agents/INDEX.md` inside it is generated the same way, by `scripts/install/install_agents.sh --index-only` |
| `plugins/` | operators who opt into the extras bundle (specialist agents and general engineering skills, outside the core flow) | yes | its own `plugins/drunken-extras/.claude-plugin/plugin.json` manifest; no generator |
| `src/core/templates/` | new projects — what `drunken-init` writes into them | yes | packaged into the wheel via `pyproject.toml`'s `[tool.setuptools.package-data]` (`core = ["templates/*.md"]`), because the installed tool carries only `src` (DG-392); `src/core/scaffold.py` reads it to write a project's `AGENTS.md` and `CLAUDE.md` |
| `templates/` | copy-paste material a person copies into their own project by hand, for a tool `drunken-init` does not configure | yes | `scripts/check_doc_drift.py` scans it deliberately, suffix or not, because a stale instruction here propagates into every project it is copied into. **LEGACY, retired (DG-427):** `CLAUDE.md` (211 lines) predated REQ-015's one-line adapter and restated rules a project's own `AGENTS.md` now owns — moved out of this folder; `RETIRED.md` names it. Every other file's own reader inventory is in the "Templates root" section below |
| `examples/` | reference material — the flow and its filled-in setup documents, for a fictional app | yes | none; `examples/README.md` explains the set (who it's for, the flow walkthrough) |
| `scripts/install/` | the operator installing skills and agents to `~/.claude/` | yes | `tests/test_install_index_determinism.py` checks what it generates (`skills/INDEX.md`, `agents/INDEX.md`) is reproducible |

**`src/core/templates/` is the one canonical folder** — what `drunken-init` actually writes into a
project (`AGENTS.md`, and the one-line `CLAUDE.md` adapter), and the only location packaged into
the installed wheel (DG-392). `templates/` at the root is not a second canonical set decided into
a permanent pair with it: every file still there stays only for the stated reason in its own row
below, not by default, and DG-427 moved a file out the moment its reason stopped holding.

## Templates root — per-file inventory (DG-427)

Every file under `templates/`, who reads it today (grepped against the whole tree, not assumed),
and the decision: retired (nothing read it, or every reader was fixed to stop), left at root
(something real reads it and `drunken-init` does not produce it, so there is nothing of
`drunken-init`'s to fold it into), or a recommendation to move into `src/core/templates/` for the
Boss to decide (none currently — nothing forces it).

| file | readers | true under REQ-006 / REQ-015? | decision |
|---|---|---|---|
| `CLAUDE.md` | *(retired)* was `GETTING_STARTED.md`, `.claude/rules/ai-layer.md` | no — a 211-line rulebook restating coordination rules the project's own `AGENTS.md` now owns, against a one-line adapter | **retired** (DG-427): every reader above rewritten to stop pointing at it, then moved to `_not_used/`; `RETIRED.md` names it |
| `.cursorrules` | `GETTING_STARTED.md`, `Integration-Guide.md`, this table, `scripts/check_doc_drift.py` (scans it), `tests/test_doc_drift.py`, `tests/test_instruction_file_pointers.py` | yes — thin, points at `AGENTS.md` as the authority, states nothing `AGENTS.md` does not | **left at root**: copy-paste for Cursor, which `drunken-init` does not configure — nothing to fold into `src/core/templates/` |
| `CONVENTIONS.md` | same as `.cursorrules`, plus `templates/.aider.conf.yml` (loads it every Aider session), `src/core/ai_layer.py` and `tests/test_ai_layer.py` (both describe the pairing) | yes — defers to `AGENTS.md`, carries only what differs for Aider | **left at root**: Aider-only, paired with `.aider.conf.yml`; same reasoning |
| `.aider.conf.yml` | same readers as `CONVENTIONS.md` | yes — reads `AGENTS.md` and `CONVENTIONS.md`, turns off Aider's own commits | **left at root**: Aider-only; `drunken-init` never writes an Aider config |
| `claude-session-hook.md` | `tests/test_session_hook_template.py` | yes — is explicit that it is a Claude-only extra, not part of the vendor-neutral `AGENTS.md` (REQ-006), and that an agent hands the snippet to the Boss rather than installing it | **left at root**: Claude-only by its own stated reason; nothing to consolidate |
| `SESSION_CHECKPOINT.md` | `AGENTS.md`, `Integration-Guide.md`, `DESIGN.md`, `docs/REFERENCE.md`, `skills/workflow/session-checkpoint/SKILL.md`, `.gitignore`, `scripts/check_ignored_sources.py` (comment), `src/jira_mcp/server.py` (prompt) | yes — a per-session, machine-local handoff note; the root instance is ignored and the tracked template is only a blank seed | **left at root**: `drunken-init` writes permanent instruction files only, never a session scratch note |
| `PROJECT_BRIEF.md` | `GETTING_STARTED.md`, `Integration-Guide.md`, `skills/flow/prd/SKILL.md`, `skills/documents/project-docs/SKILL.md`, `tests/test_agents_md_pointers.py` (anchored sentence) | yes — optional pre-`/prd` drafting material, `/prd` reads and offers to consolidate it, nothing invents it as decided | **left at root**: not something `drunken-init` produces — `/prd` and a person writing it by hand are the only producers |
| `REQUIREMENTS.md` | same as `PROJECT_BRIEF.md` | yes — same reasoning | **left at root**: same reasoning |
| `ci/dependency-audit.yml`, `ci/dependency-audit.md` | `.github/workflows/dependency-audit.yml` (this repository's own adapted instance, says so in its own header comment), `scripts/detect_dependency_manifests.py` | yes — CI copy-paste material for a downstream project's own GitHub Actions, unrelated to `AGENTS.md`/`CLAUDE.md` entirely | **left at root**, untouched: no reference to update, and out of this ticket's blast radius either way |

Mechanically checked by `tests/test_readme_templates_inventory.py`: every file that exists under
`templates/` (recursively) has a row above, and every row names a file that exists — a file added
or removed from `templates/` without updating this table fails the suite.
