# Contributing to Drunken AGY Inn

First off, thank you for considering contributing to Drunken AGY Inn! It's people like you who make this toolkit better for everyone.

---

## 📜 Code of Conduct

By participating in this project, you agree to abide by our [Code of Conduct](CODE_OF_CONDUCT.md). Please report any unacceptable behavior to the project maintainers.

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

### 0. Local Safety Hooks (Recommended)
To prevent accidental direct pushes to protected branches (`main`, `develop`), install the local Git hooks:
```bash
python3 scripts/setup_git_hooks.py
```
This installs a local `pre-push` Git hook that automatically intercepts direct push attempts to protected branches and blocks them, reminding you to open a Pull Request.

### 1. Branch Structure
*   **`main`**: Represents the stable, production-ready release state. Do not commit directly here.
*   **`develop`**: The primary integration branch for active development and features. All PRs must target this branch.

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
4.  **Create a Pull Request (PR):** Create a PR targeting the `develop` branch of the main repository.
    *   **Using GitHub CLI (`gh`):**
        ```bash
        gh pr create --head feature/your-feature-name --base develop --title "feat: your feature summary" --body "Detailed description of changes"
        ```
    *   *Direct pushes to `main` and `develop` branches are blocked by branch protection hooks. Changes must go through the Pull Request flow.*

### 3. Review & Merging (PR Flow)
*   All Pull Requests require at least **1 approving review** from a repository owner/maintainer.
*   **Merging PRs:** Once approved and ready:
    *   **Using GitHub CLI (`gh`):**
        ```bash
        gh pr merge <pr-number> --merge
        ```
    *   *If administrative privileges are required to bypass rules on protected branches, admins can use the `--admin` flag:*
        ```bash
        gh pr merge <pr-number> --merge --admin
        ```

### 4. Release Workflow
Releases are created by merging `develop` into `main` via a Pull Request, then tagging and creating a release.

1.  Create a PR from `develop` to `main`:
    ```bash
    gh pr create --head develop --base main --title "Release vX.Y.Z: release summary" --body "Release notes details"
    ```
2.  Merge the release PR (using `--admin` if necessary):
    ```bash
    gh pr merge <pr-number> --merge --admin
    ```
3.  Tag the merge commit and push tags:
    ```bash
    git tag -a vX.Y.Z -m "Release vX.Y.Z description"
    git push origin vX.Y.Z
    ```
4.  Publish the release:
    ```bash
    gh release create vX.Y.Z -t "Release Title" -n "Release notes description"
    ```
