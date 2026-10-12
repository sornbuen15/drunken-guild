#!/usr/bin/env python3
"""DG-517 round 5. Mechanical proof that every `##`/`###` heading of the OLD
README.md and GETTING_STARTED.md (as they stood at origin/develop, the commit
this branch forked from) has a home: either the exact text survives in its
new location, or the heading is an explicitly-named, explained exception.

For each old heading, prints FOUND(file) when a verbatim marker from that
section is found in one of the current docs, or MISSING(superseded: reason)
for the handful of headings the Boss agreed could be left out. Exits 1 if any
heading is unaccounted for.

Run from the repository root:

    uv run python scripts/verify_dg517_headings.py
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CURRENT_FILES = {
    "README.md": REPO_ROOT / "README.md",
    "GETTING_STARTED.md": REPO_ROOT / "GETTING_STARTED.md",
    "docs/REFERENCE.md": REPO_ROOT / "docs" / "REFERENCE.md",
    "REPOSITORY_MAP.md": REPO_ROOT / "REPOSITORY_MAP.md",
}

#: (old heading, source file it came from, a short marker string unique to
#: that section's real content) -> checked against every file in
#: CURRENT_FILES; the first file containing the marker is reported as FOUND.
HEADINGS = [
    ("Two halves, one repository", "README.md", "They are one repository on purpose"),
    (
        "Quick start — install from a release tag (no clone)",
        "README.md",
        "drunken-install skills --prune` lists retired skills",
    ),
    (
        "Quick start — the AI layer, from a clone",
        "README.md",
        "No Python, no credentials, no server. Clone and install",
    ),
    (
        "Quick start — the runtime",
        "README.md",
        "Prove it resolves. This is a separate step",
    ),
    (
        "Where a project's AI layer comes from",
        "README.md",
        "Two things never go in the config repo",
    ),
    (
        "Giving an existing AGENTS.md the guild block",
        "README.md",
        "Add `--guild-block` to merge the block",
    ),
    (
        "Installing it as a command",
        "README.md",
        "ignores `uv.lock`, so the tool environment",
    ),
    (
        "How the AI layer is organised",
        "README.md",
        None,  # SUPERSEDED: parent heading only, no content of its own.
    ),
    ("Skills vs agents", "README.md", "Skills are the craft; agents are the craftsmen"),
    ("Three roles", "README.md", "reviewer  — one round on the plan"),
    (
        "The flow — seven commands",
        "README.md",
        "PRD.md: the brief and the requirements in one file",
    ),
    ("Skill categories", "README.md", "the skills the flow uses"),
    (
        "Repository map",
        "README.md",
        "Which directory is whose, verified against the tree",
    ),
    (
        "Templates root — per-file inventory (DG-427)",
        "README.md",
        "Every file under `templates/`, who reads it today",
    ),
    (
        "Documentation",
        "README.md",
        "`SESSION_CHECKPOINT.md`](../SESSION_CHECKPOINT.md) | where the work currently stands",
    ),
    ("Known limitations", "README.md", "Token cost and latency"),
    ("Why this exists", "README.md", "I wanted to know where AI-assisted delivery"),
    (
        "Contributing",
        "README.md",
        "Work lands on `develop` through a pull request",
    ),
    ("Table of contents", "GETTING_STARTED.md", None),  # SUPERSEDED: structural only.
    ("Prerequisites", "GETTING_STARTED.md", "A Jira account, and a Discord bot"),
    (
        "Install the AI layer",
        "GETTING_STARTED.md",
        "Verify — you should see the skill directories",
    ),
    (
        "7 of the 12 skills need nothing else",
        "GETTING_STARTED.md",
        "`/prd`, `/clarify` and `/ddd` write markdown",
    ),
    (
        "Make sure it gets used",
        "GETTING_STARTED.md",
        "A session can start in a fresh `git worktree` with no `AGENTS.md`",
    ),
    (
        "Skills not authored here",
        "GETTING_STARTED.md",
        "`skills/.external` lists skills that are installed",
    ),
    (
        "Older skills and agents",
        "GETTING_STARTED.md",
        "Sixteen general engineering skills and fifteen domain-specialist agents",
    ),
    (
        "Add the runtime (optional)",
        "GETTING_STARTED.md",
        "claude mcp list        # drunken-jira-mcp",
    ),
    (
        "Step 1 — Set up the project's rules",
        "GETTING_STARTED.md",
        "Where these files come from",
    ),
    ("Step 2 — Write the PRD", "GETTING_STARTED.md", "This step writes no Jira ticket"),
    (
        "Step 3 — Answer the questions only you can answer",
        "GETTING_STARTED.md",
        "about ten\nranked questions",
    ),
    (
        "Step 4 — Agree the vocabulary",
        "GETTING_STARTED.md",
        "Each context becomes exactly one Epic",
    ),
    (
        "Step 5 — Cut the backlog",
        "GETTING_STARTED.md",
        "It probes `jira_board_info` first",
    ),
    (
        "Step 6 — Build one task",
        "GETTING_STARTED.md",
        "jira_submit_for_review` — the ticket goes",
    ),
    (
        "Step 7 — Audit what actually shipped",
        "GETTING_STARTED.md",
        "Merged is not deployed",
    ),
    (
        "Mid-sprint scenarios",
        "GETTING_STARTED.md",
        "A bug comes through the same skill that cut the backlog",
    ),
    ("Using the three roles", "GETTING_STARTED.md", "claude --agent manager"),
    (
        "Where to go next",
        "GETTING_STARTED.md",
        None,  # SUPERSEDED: structural, replaced by each file's own table.
    ),
]

SUPERSEDED_REASONS = {
    "How the AI layer is organised": "parent heading only; every real child section "
    "(Skills vs agents, Three roles, The flow, Skill categories) is accounted for "
    "separately below",
    "Table of contents": "structural navigation only, no unique content; the new "
    "docs/REFERENCE.md has its own Contents list",
    "Where to go next": "structural; README.md and GETTING_STARTED.md each still "
    "carry their own 'Where to go next' table, and the extra rows that table used "
    "to carry (CONFIG_REPO.md, examples/, SESSION_CHECKPOINT.md) moved into the "
    "'Full documentation index' section instead",
}


def _normalize(text: str) -> str:
    return " ".join(text.split())


def main() -> int:
    contents = {
        name: path.read_text(encoding="utf-8") for name, path in CURRENT_FILES.items()
    }
    normalized = {name: _normalize(text) for name, text in contents.items()}

    unaccounted: list[str] = []
    for heading, source, marker in HEADINGS:
        if marker is None:
            reason = SUPERSEDED_REASONS.get(heading, "no reason recorded")
            print(f"MISSING(superseded: {reason}) -- {heading!r} ({source})")
            continue

        marker_norm = _normalize(marker)
        found_in = next(
            (name for name, text in normalized.items() if marker_norm in text), None
        )
        if found_in:
            print(f"FOUND({found_in}) -- {heading!r} ({source})")
        else:
            unaccounted.append(heading)
            print(f"MISSING(unexplained!) -- {heading!r} ({source})")

    print()
    if unaccounted:
        print(f"{len(unaccounted)} heading(s) unaccounted for: {unaccounted}")
        return 1
    print(f"All {len(HEADINGS)} old headings accounted for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
