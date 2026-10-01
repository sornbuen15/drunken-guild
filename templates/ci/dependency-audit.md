# Dependency Audit workflow

**What this is:** a scheduled, multi-language dependency audit —
`dependency-audit.yml` in this same directory — covering Python, PHP and
Node, plus the repository's own Dependabot alerts. DG-415, requirement
REQ-018: one tool is not enough — on 2026-10-01 pip-audit reported nothing
for a lockfile that Dependabot held two open alerts against, and a sibling
project has Dependabot switched off entirely, so nothing there reports at
all. This runs the audits that apply and says plainly which it could not
reach.

drunken-guild runs its own copy of this file, unmodified, at
`.github/workflows/dependency-audit.yml` — the template is proven on this
repository before anyone else copies it.

## What it does

1. **Detects manifests.** `uv.lock` or `requirements*.txt` → Python,
   `composer.lock` → PHP, `package-lock.json` → Node. A project with only
   one of these runs only the matching audit; the others are skipped and
   said to be skipped, not silently absent.
2. **Runs the audits that apply:**
   - `pip-audit --strict` — against `uv.lock` (exported the same way
     `.github/workflows/test.yml`'s `security` job does, auditing what a
     user actually installs, not a hand-maintained file that can drift from
     it — DG-289) or, with no `uv.lock`, against each `requirements*.txt`
     directly.
   - `composer audit`.
   - `npm audit --omit=dev`.
3. **Reads the repository's open Dependabot alerts** with `gh api`. A 403 or
   404 means Dependabot alerts are not enabled, or this token cannot see
   them — reported plainly, not treated as a workflow failure.
4. **Fails the run on any finding**, from any step. There is no auto-merge
   and no auto-upgrade anywhere in this file — a finding is a decision for a
   person.

## Copying it into a project

Copying the file is a pull request the project's owner reviews and merges,
same as any other change — this template does not install itself.

A copying project needs to bring:

- `dependency-audit.yml` itself, into `.github/workflows/`.
- `scripts/detect_dependency_manifests.py` from drunken-guild's own
  `scripts/` — the detect step calls it directly rather than repeating the
  manifest logic as inline shell, which is also what makes the logic
  testable (see `tests/test_detect_dependency_manifests.py` in
  drunken-guild for the fixture-directory tests this script is proven
  against). A project without `python3` on its runners needs an equivalent
  step; the hosted `ubuntu-latest` image carries Python by default, so most
  projects need nothing extra.

**Turning Dependabot alerts on is a repository setting, not something this
workflow — or any agent — can do.** Settings → Code security → Dependabot
alerts, in the GitHub UI, by a person with admin on the repository. Until
that is on, the `dependabot-alerts` job reports "not enabled" every run,
correctly, and that is not a bug in the workflow.

## Permissions

`contents: read` at the workflow level — every audit step reads the
checkout and nothing writes anywhere. The `dependabot-alerts` job adds
`security-events: read`, because `GET /repos/{owner}/{repo}/dependabot/alerts`
requires it; that grant sits on the one job that calls the endpoint, not on
the workflow as a whole, so a reviewer can see exactly which job needs the
extra scope without it being handed to the audits that do not.

## Dispatching it

A workflow only becomes dispatchable from the GitHub UI once it exists on
the repository's default branch — `workflow_dispatch` on a branch that is
only a pull request is not reachable that way. The manual run that proves
this is green on a clean tree, and red once a known-vulnerable pin is
introduced on a scratch branch, has to happen **after this merges to
`develop`**, or on the PR branch if GitHub's "Use workflow from" branch
picker allows targeting it before merge. Either way, it is the Boss's call
to run and to report back, not a claim an agent can make for a PR that is
still open.
