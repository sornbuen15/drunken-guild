# Contributing to Drunken Guild

First off, thank you for considering contributing to Drunken Guild! It's people like you who make this toolkit better for everyone.

---

## 📜 Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to the project maintainers.

---

## 🔧 Development Setup

Working from a clone is the contributor path — a user installs a release tag instead (see
[README.md](./README.md#install)); this is the only place that story is told:

```bash
git clone https://github.com/sornbuen15/drunken-guild.git
cd drunken-guild
uv sync --extra dev
pre-commit install
```

`--extra dev` is not optional if you intend to run the tests — without it `uv run pytest` can fall
through to whatever `pytest` is on `PATH`. `uv run drunken-install all --dry-run` and
`uv run drunken-doctor` work the same from a clone as from an installed tool; the full credential
and registry setup is in [Drunken-Guild-Guide.md](./Drunken-Guild-Guide.md#2-registry-credentials-and-the-mcp-server).

---

## 🛠️ How Can I Contribute?

### Reporting Bugs
* **Check existing issues/discussions** to see if the bug has already been reported.
* If it hasn't, open a new issue. Include a clear title, a description of the bug, steps to reproduce, and any relevant logs or screenshots.

### Suggesting Enhancements
* Open a new discussion under the **Ideas** category in GitHub Discussions to brainstorm with the community.
* If the idea gains traction, we can formulate it into a structured task and track it.

---

## 🌳 Git Branching & Workflow Rules

We follow a strict development and pull request workflow to maintain code quality, security, and stability.

### 0. Local Gates (Required)
Install pre-commit in a fresh clone. Without it the local gates — ruff, ruff-format, mypy — do not
run at all, and say nothing:
```bash
pre-commit install
```

You do not need a local hook to protect `main` and `develop`. GitHub rulesets on both branches
require a pull request and passing checks, block force-push and deletion, and list no bypass
actors, so a direct push is refused by the server. A local hook would duplicate a control that
cannot be bypassed with one that can — by not being installed.

### 1. Branch Structure
*   **`main`**: Out of scope for this project work. Do not push to it, open PRs targeting it, or merge into it.
*   **`develop`**: The integration branch for active development. Authorized review requests target this branch; a human decides whether to merge.

### 2. Feature & Fix Branching Workflow
Always follow these steps when working on changes:

1.  **Branch Out:** Create a new branch off of `develop`.
    ```bash
    git checkout develop
    git pull origin develop
    git checkout -b feature/your-feature-name  # or bugfix/your-fix-name
    ```
2.  **Commit Conventions:** Make clear, descriptive commits. Do not commit hardcoded credentials or local paths.
3.  **Push Branch:** Push your branch to the remote repository.
    ```bash
    git push -u origin feature/your-feature-name
    ```
4.  **Create a Pull Request (PR):** When authorized, create a PR targeting `develop`.
    *   **Using GitHub CLI (`gh`):**
        ```bash
        gh pr create --head feature/your-feature-name --base develop --title "feat: your feature summary" --body "Detailed description of changes"
        ```
    *   *Direct pushes to `main` and `develop` branches are blocked by branch protection hooks. Changes must go through the Pull Request flow.*

### 3. Review & Merging
*   A human reviews changes and decides whether to merge into `develop`.
*   Agents do not merge. No workflow or release step in this guide targets `main`.

### 4. Release Workflow
Release policy is intentionally not part of this feature work. Do not tag, publish, or merge into
`main` without a separate explicit project decision.
