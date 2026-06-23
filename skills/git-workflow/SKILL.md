---
name: git-workflow
description: Standardized Git branching, Pull Requests, releases, and GitHub CLI (gh) best practices
---

# Git & GitHub CLI Standard Workflow

Apply these rules and command patterns whenever committing code, creating pull requests, managing releases, or tagging versions in this repository.

## 1. Branching Model

- `main`: Represents the stable, production-ready release state. Never commit or push directly to `main`.
- `develop`: The active integration branch. All feature branches and bug fixes must branch off and merge back into `develop`.
- `feature/<name>` or `bugfix/<name>`: Individual working branches for developers.

## 2. Local Safety Hook Installation

To enforce these protections locally and prevent accidental direct pushes to protected branches, run:
```bash
python3 scripts/setup_git_hooks.py
```
This installs a local Git `pre-push` hook that intercepts direct pushes to `main` and `develop`.

## 3. Pull Request Workflow (Feature -> develop)

1. **Update Local State**:
   ```bash
   git checkout develop
   git pull origin develop
   ```
2. **Create Working Branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```
3. **Commit & Push**:
   ```bash
   git add .
   git commit -m "prefix: descriptive message"
   git push -u origin feature/your-feature-name
   ```
4. **Create PR to `develop`**:
   Use GitHub CLI (`gh`):
   ```bash
   gh pr create --head feature/your-feature-name --base develop --title "feat: summary" --body "description"
   ```
5. **Merge PR**:
   Once approved or after meeting requirements:
   ```bash
   gh pr merge <pr-number> --merge
   # Use --admin if admin override is needed:
   gh pr merge <pr-number> --merge --admin
   ```

## 4. Release Workflow (develop -> main)

1. **Create Release PR**:
   Create a Pull Request from `develop` to `main`:
   ```bash
   gh pr create --head develop --base main --title "Release vX.Y.Z" --body "Release notes details"
   ```
2. **Merge Release PR**:
   ```bash
   gh pr merge <pr-number> --merge --admin
   ```
3. **Tag & Publish Release**:
   Locally pull the updated `main`, tag it, push the tag, and publish the release:
   ```bash
   git checkout main
   git pull origin main
   git tag -a vX.Y.Z -m "Release vX.Y.Z description"
   git push origin vX.Y.Z
   gh release create vX.Y.Z -t "Release Title" -n "Release notes description"
   ```
