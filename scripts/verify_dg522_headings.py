#!/usr/bin/env python3
"""DG-522. Mechanical proof that every `##`/`###` heading of the OLD
Drunken-Guild-Guide.md and Integration-Guide.md (as they stood at
`origin/develop`, the commit this branch forked from) has a home: either the
exact text survives in its new location, or the heading is an
explicitly-named, explained exception.

For each old heading, prints FOUND(file) when a verbatim marker from that
section is found in one of the current docs, or MISSING(superseded: reason)
for the headings the Boss agreed could be folded elsewhere or dropped. Exits
1 if any heading is unaccounted for.

Run from the repository root:

    uv run python scripts/verify_dg522_headings.py
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

CURRENT_FILES = {
    "README.md": REPO_ROOT / "README.md",
    "GETTING_STARTED.md": REPO_ROOT / "GETTING_STARTED.md",
    "Drunken-Guild-Guide.md": REPO_ROOT / "Drunken-Guild-Guide.md",
    "Integration-Guide.md": REPO_ROOT / "Integration-Guide.md",
    "CONTRIBUTING.md": REPO_ROOT / "CONTRIBUTING.md",
    "docs/REFERENCE.md": REPO_ROOT / "docs" / "REFERENCE.md",
    "RETIRED.md": REPO_ROOT / "RETIRED.md",
}

#: (old heading, source file it came from, a short marker string unique to
#: that section's real content) -> checked against every file in
#: CURRENT_FILES; the first file containing the marker is reported as FOUND.
HEADINGS = [
    # --- Drunken-Guild-Guide.md, as it stood at origin/develop ---
    (
        "1. What Drunken-Guild Is",
        "Drunken-Guild-Guide.md",
        None,  # SUPERSEDED: see below.
    ),
    ("2. Architecture", "Drunken-Guild-Guide.md", "`src/core/registry.py`"),
    (
        "2.1 AI behavior boundaries",
        "Drunken-Guild-Guide.md",
        "is\nonly the one-line adapter that imports it",
    ),
    ("3. Installation & Setup", "Drunken-Guild-Guide.md", None),  # SUPERSEDED
    (
        "3.1 Prerequisites",
        "Drunken-Guild-Guide.md",
        "A Jira account, and a Discord bot",
    ),
    (
        "3.2 Clone and install dependencies",
        "Drunken-Guild-Guide.md",
        "git clone https://github.com/sornbuen15/drunken-guild.git",
    ),
    (
        "3.3 Configure credentials",
        "Drunken-Guild-Guide.md",
        "takes `file://path#key.path`, `env://VAR`, `op://vault/item/field` or",
    ),
    (
        "3.4 Register the MCP servers (for an AI coding agent)",
        "Drunken-Guild-Guide.md",
        None,  # SUPERSEDED
    ),
    (
        "3.6 Prove it works, before trusting it",
        "Drunken-Guild-Guide.md",
        "asks `/rest/api/3/myself`, which 401s",
    ),
    ("4. Jira Workflow", "Drunken-Guild-Guide.md", None),  # SUPERSEDED
    (
        "4.1 The `drunken-jira-mcp` tools (supported path)",
        "Drunken-Guild-Guide.md",
        "| claim and start | `jira_start_task` |",
    ),
    (
        "4.2 The full lifecycle for one ticket",
        "Drunken-Guild-Guide.md",
        "git checkout -b feature/DG-42-short-description",
    ),
    (
        "5. Notifications and approvals",
        "Drunken-Guild-Guide.md",
        "Discord is **one-way**",
    ),
    (
        "6. Multi-Project Orchestration",
        "Drunken-Guild-Guide.md",
        'answers "which Jira, which repo, which webhook" for every project',
    ),
    (
        "7. The quality gate",
        "Drunken-Guild-Guide.md",
        "A ticket is Done when its test was",
    ),
    (
        "8. Where to Go Next",
        "Drunken-Guild-Guide.md",
        "[Integration Guide](./Integration-Guide.md)",
    ),
    # --- Integration-Guide.md, as it stood at origin/develop ---
    (
        "1. The MCP Servers",
        "Integration-Guide.md",
        "Drunken-Guild exposes two separate MCP servers",
    ),
    (
        "`drunken-jira-mcp` -- Jira operations",
        "Integration-Guide.md",
        "jira_daily_standup",
    ),
    (
        "Approvals -- no server, and nothing to call",
        "Integration-Guide.md",
        'python -m core.notify "<line>" --link <url>',
    ),
    (
        "2. Local AI Configuration Templates",
        "Integration-Guide.md",
        "templates/SESSION_CHECKPOINT.md",
    ),
    (
        "3. Workflow Handoff",
        "Integration-Guide.md",
        "jira_submit_for_review(issue_key, pr_link, files_changed)",
    ),
    (
        "4. Integrating an Existing (Non-Drunken-Guild) Project",
        "Integration-Guide.md",
        "bring an existing project under this same workflow",
    ),
    (
        "Step 1: Install Drunken-Guild's CLI tools",
        "Integration-Guide.md",
        "drunken-doctor --requirements",
    ),
    (
        "Step 2: Onboard the project",
        "Integration-Guide.md",
        "onboard_project.py existing-project",
    ),
    (
        "Step 2b: Prove it, before trusting it",
        "Integration-Guide.md",
        "asks `/rest/api/3/myself`, which 401s",
    ),
    (
        "Step 3: Copy the templates",
        "Integration-Guide.md",
        "fill `AGENTS.md`'s build and test commands",
    ),
    (
        "Step 4: The MCP server",
        "Integration-Guide.md",
        "claude mcp add --scope user drunken-jira-mcp",
    ),
]

SUPERSEDED_REASONS = {
    "1. What Drunken-Guild Is": "the three-bullet product description now lives once, "
    "shared verbatim in intent with README.md's own opening, which this page's new "
    "intro points at and restates in the same terms (skills, roles, the seven-command "
    "flow, Jira, hooks); the per-component facts moved into the Architecture table",
    "3. Installation & Setup": "parent heading only; the install story itself moved out "
    "entirely -- a user installs a release tag (README.md, GETTING_STARTED.md) and a "
    "contributor clones (CONTRIBUTING.md), which is the one-install-story fix this "
    "ticket's FINDING asked for. Credentials and the MCP server, the parts that are "
    "this page's own job, are now §2",
    "3.4 Register the MCP servers (for an AI coding agent)": "the per-checkout "
    "`.mcp.json` generation this section instructed (`install_mcp.sh --out .mcp.json`) "
    "contradicted the Decided 2026-10-10 rule the rest of the repository already "
    "followed (REQ-019, DG-457): a project carries none, the server is declared once "
    "per machine. That is also the exact bug this ticket's FINDING named -- §3.4 "
    "depended on §3.2 running `uv tool install .`, which §3.2 never did. The surviving "
    "fact, that the project id travels per call and not per server (DG-341), is in this "
    "page's new §2; what was retired and why is RETIRED.md, not restated here",
    "4. Jira Workflow": "parent heading only; both real children (the tool table and the "
    "lifecycle) are accounted for separately below, now under §3",
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
