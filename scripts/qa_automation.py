#!/usr/bin/env python3
import json
import re
import subprocess
import time
from typing import Any, cast


def _matches_ticket_key(issue_key: str, text: str) -> bool:
    """True if `issue_key` appears in `text` as a whole ticket key, not as a
    substring of a longer one (e.g. "DT-6" must not match "DT-65")."""
    pattern = rf"(?<![A-Za-z0-9-]){re.escape(issue_key)}(?!\d)"
    return re.search(pattern, text) is not None


def run_command(cmd: list[str]) -> tuple[int, str, str]:
    print(f"Running: {' '.join(cmd)}")
    result = subprocess.run(cmd, capture_output=True, text=True)
    return result.returncode, result.stdout, result.stderr


def get_in_review_issues() -> list[dict[str, Any]]:
    code, stdout, stderr = run_command(
        ["python", "scripts/jira_bridge.py", "get-in-review"]
    )
    if code != 0:
        print(f"Failed to get in-review issues: {stderr}")
        return []
    try:
        return cast(list[dict[str, Any]], json.loads(stdout))
    except json.JSONDecodeError:
        print(f"Failed to parse jira output: {stdout}")
        return []


def get_open_prs() -> list[dict[str, Any]]:
    code, stdout, stderr = run_command(
        ["gh", "pr", "list", "--state", "open", "--json", "number,headRefName,title"]
    )
    if code != 0:
        print(f"Failed to get open PRs: {stderr}")
        return []
    try:
        return cast(list[dict[str, Any]], json.loads(stdout))
    except json.JSONDecodeError:
        print(f"Failed to parse gh pr output: {stdout}")
        return []


_UV_ENV_ERROR_MARKERS = (
    "No solution found when resolving",
    "requirements are unsatisfiable",
    "error: Failed to",
)


def _uv_env_error(stderr: str) -> str | None:
    """If `uv run` failed because it couldn't resolve the branch's own
    environment (not because the tool it ran reported a real failure),
    return an explanatory message; otherwise None.

    This is reachable in practice: `review_issue()` checks out each
    ticket's OWN branch and tests it in isolation, before it's been merged
    onto current develop. A branch cut before a dependency/Python-version
    fix landed (this repo has several) won't resolve under `uv run` at
    all -- that's an environment problem, not a defect in the ticket's
    code, and must not be reported as one.
    """
    if any(marker in stderr for marker in _UV_ENV_ERROR_MARKERS):
        return (
            "Could not resolve this branch's project environment via `uv run` "
            "(error below) -- this usually means the branch was cut before a "
            "dependency/tooling fix landed on develop and needs to be rebased, "
            "not that the ticket's own code is broken:\n" + stderr
        )
    return None


def run_tests() -> tuple[bool, str]:
    print("Running QA checks (pytest, ruff, mypy)...")
    # `uv run` on purpose, not bare commands: this gate must check against
    # the exact tool versions this project's dependencies resolve to, not
    # whatever happens to be on the runner's PATH (a global/pyenv-shimmed
    # ruff can disagree with the project's pinned version on lint rules
    # like import grouping, producing a false failure that has nothing to
    # do with the actual code change being validated).
    test_code, test_out, test_err = run_command(["uv", "run", "pytest"])
    if test_code != 0:
        env_error = _uv_env_error(test_err)
        if env_error:
            return False, env_error
        return False, f"Pytest failed:\n{test_out}\n{test_err}"

    ruff_code, ruff_out, ruff_err = run_command(["uv", "run", "ruff", "check", "."])
    if ruff_code != 0:
        return False, f"Ruff failed:\n{ruff_out}\n{ruff_err}"

    mypy_code, mypy_out, mypy_err = run_command(["uv", "run", "mypy", "."])
    if mypy_code != 0:
        return False, f"Mypy failed:\n{mypy_out}\n{mypy_err}"

    return True, "All QA checks passed successfully."


def review_issue(issue: dict[str, Any], prs: list[dict[str, Any]]) -> dict[str, Any]:
    """Run the per-ticket QA gate: checkout its branch, run the suite in isolation,
    and leave a review on its PR. This alone does NOT clear the ticket for Done --
    see run_integration_check for the round-level gate that does.
    """
    issue_key = issue["key"]
    print(f"Processing issue: {issue_key}")

    matching_pr = None
    for pr in prs:
        if _matches_ticket_key(issue_key, pr["headRefName"]) or _matches_ticket_key(
            issue_key, pr["title"]
        ):
            matching_pr = pr
            break

    if not matching_pr:
        print(f"No open PR found for {issue_key}")
        return {
            "key": issue_key,
            "pr_number": None,
            "branch": None,
            "passed": False,
            "skipped": True,
            "message": "No open PR found for this ticket.",
        }

    pr_number = str(matching_pr["number"])
    branch_name = matching_pr["headRefName"]
    print(f"Found PR #{pr_number} on branch {branch_name} for {issue_key}")

    run_command(["git", "fetch", "origin", branch_name])
    # -B forces the local branch to match origin/branch_name exactly (create
    # or reset), instead of `checkout branch_name` which silently keeps
    # stale local commits if the local branch already existed — this QA
    # runner is persistent across rounds, so that staleness is reachable.
    run_command(["git", "checkout", "-B", branch_name, f"origin/{branch_name}"])

    passed, message = run_tests()

    if passed:
        print(f"Individual QA passed for {issue_key}")
        run_command(
            [
                "gh",
                "pr",
                "review",
                pr_number,
                "--approve",
                "-b",
                "✅ QA Automation: Individual checks passed. "
                "Holding for round-level integration test before Done.",
            ]
        )
    else:
        print(f"Individual QA failed for {issue_key}")
        run_command(
            [
                "gh",
                "pr",
                "review",
                pr_number,
                "--request-changes",
                "-b",
                f"❌ QA Automation: Checks failed.\n```\n{message}\n```",
            ]
        )
        run_command(
            ["python", "scripts/jira_bridge.py", "transition", issue_key, "In Progress"]
        )

    run_command(["git", "checkout", "develop"])
    print("-" * 40)

    return {
        "key": issue_key,
        "pr_number": pr_number,
        "branch": branch_name,
        "passed": passed,
        "skipped": False,
        "message": message,
    }


def run_integration_check(passed_results: list[dict[str, Any]]) -> tuple[bool, str]:
    """Merge every branch that passed its individual QA gate onto one scratch
    branch off develop and re-run the full suite there. This is the mandatory
    proof that the round works together, not just that each ticket passes alone
    -- a ticket only reaches Done once this passes.
    """
    integration_branch = f"qa/integration-{int(time.time())}"

    # fetch + hard reset instead of `git pull`: pull can fail or create an
    # unexpected merge commit if local develop has diverged/has local
    # changes; this runner only ever needs develop to exactly match origin.
    run_command(["git", "fetch", "origin", "develop"])
    run_command(["git", "checkout", "-B", "develop", "origin/develop"])
    code, _, err = run_command(["git", "checkout", "-b", integration_branch])
    if code != 0:
        return False, f"Failed to create integration branch:\n{err}"

    for result in passed_results:
        code, out, err = run_command(
            ["git", "merge", "--no-ff", "--no-edit", f"origin/{result['branch']}"]
        )
        if code != 0:
            run_command(["git", "merge", "--abort"])
            run_command(["git", "checkout", "develop"])
            run_command(["git", "branch", "-D", integration_branch])
            return (
                False,
                f"Merge conflict combining {result['key']} ({result['branch']}) "
                f"with the rest of the round:\n{out}\n{err}",
            )

    passed, message = run_tests()

    run_command(["git", "checkout", "develop"])
    run_command(["git", "branch", "-D", integration_branch])

    return passed, message


def build_round_report(
    all_results: list[dict[str, Any]],
    integration_passed: bool,
    integration_message: str,
) -> str:
    lines = ["QA Round Report", ""]
    lines.append("Tasks in this round:")
    for r in all_results:
        if r["skipped"]:
            status = "skipped (no open PR)"
        elif r["passed"]:
            status = "individual QA passed"
        else:
            status = "individual QA failed"
        lines.append(f"- {r['key']}: {status}")
    lines.append("")
    lines.append("Integration test (all round changes combined):")
    if integration_passed:
        lines.append("Passed -- the round works together end-to-end, no bugs found.")
    else:
        lines.append(f"Failed:\n{integration_message}")
    return "\n".join(lines)


def main() -> None:
    print("Starting QA Validation Loop...")
    issues = get_in_review_issues()
    if not issues:
        print("No issues in 'In Review' state.")
        return

    prs = get_open_prs()

    all_results = [review_issue(issue, prs) for issue in issues]
    passed_results = [r for r in all_results if r["passed"] and not r["skipped"]]

    if not passed_results:
        print("No issues passed individual QA this round. Nothing to integrate.")
        return

    print("=" * 40)
    print(
        f"Running round-level integration test across {len(passed_results)} branch(es)..."
    )
    integration_passed, integration_message = run_integration_check(passed_results)

    report = build_round_report(all_results, integration_passed, integration_message)
    print(report)

    for result in passed_results:
        issue_key = result["key"]
        run_command(["python", "scripts/jira_bridge.py", "comment", issue_key, report])
        if integration_passed:
            run_command(
                ["python", "scripts/jira_bridge.py", "transition", issue_key, "Done"]
            )
            print(f"{issue_key}: transitioned to Done.")
        else:
            run_command(
                [
                    "python",
                    "scripts/jira_bridge.py",
                    "transition",
                    issue_key,
                    "In Progress",
                ]
            )
            print(f"{issue_key}: integration failed -- sent back to In Progress.")


if __name__ == "__main__":
    main()
