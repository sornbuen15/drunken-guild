---
name: release-notes-writer
description: Standardizes the generation of professional, readable Release Notes and Tag Version descriptions using markdown tables and clear categorizations.
---

# Release Notes Writer Skill

## Context
Whenever a new version of a project is released or tagged (e.g., `v1.2.0`), "The Boss" requires a standardized, professional, and highly readable Release Note. Good release notes serve as historical documentation and a clear communication tool for the team and stakeholders.

## Goal
Generate a comprehensive Release Note document using a standardized Markdown template that clearly communicates What's New, What's Fixed, Updates, and Deprecations.

## Standard Release Note Template
Always structure the release notes using the following format:

### 1. Header & Version
- Start with a clear H1 title: `# Release [Version Number]: [Catchy Release Name/Theme]`
- Include the release date.

### 2. Executive Summary (Highlight)
- 1-2 short paragraphs summarizing the core focus of this release. What is the most exciting or important change?

### 3. Changelog Table (The Core)
Use a Markdown Table to list all changes. The table must have 3 columns:
- **Type**: Use an emoji + category (🚀 Feature, 🐞 Bug Fix, 🔄 Update, 🗑️ Deprecate, 🛡️ Security)
- **Description**: A clear, human-readable explanation of the change.
- **Reference**: The PR number, Jira Ticket, or commit hash (e.g., `#12`, `TWA-17`).

**Example Table:**
| Type | Description | Reference |
| :--- | :--- | :--- |
| 🚀 Feature | Added Mina AI Router for Natural Language task delegation | #13 |
| 🐞 Bug Fix | Resolved UI state synchronization bug on the Web Dashboard | #12 |
| 🔄 Update | Refactored `discord_listener.py` to use asynchronous polling | #10 |
| 🗑️ Deprecate | Removed the strict `<who> <context> <goal>` string parsing | #13 |

### 4. Breaking Changes & Migration Guide (If Applicable)
- Use a `> [!WARNING]` or `> [!CAUTION]` alert block.
- Clearly state if an API changed, a config is removed, or if the user needs to manually clear caches/restart services.
- Provide step-by-step instructions on how to migrate.

### 5. Technical Details (Optional)
- Briefly mention any significant underlying infrastructure changes or dependency bumps (e.g., Updated Node to v20).

## Execution Steps
1. **Gather Context**: Read the recent Git commits, PR titles, or ask the user for the scope of the release.
2. **Categorize**: Group the changes into Features, Fixes, Updates, and Deprecations.
3. **Format**: Apply the Standard Release Note Template.
4. **Output**: Present the formatted Release Note to The Boss. If generating it for a GitHub Release, output the exact markdown block that can be copy-pasted into the GitHub Release form or `gh release create` command.

## Tone
- Professional, celebratory, and highly structured.
