#!/usr/bin/env python3
import json
import subprocess
from typing import Any, cast


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


def run_tests() -> tuple[bool, str]:
    print("Running QA checks (pytest, ruff, mypy)...")
    # Run tests
    test_code, test_out, test_err = run_command(["pytest"])
    if test_code != 0:
        return False, f"Pytest failed:\n{test_out}\n{test_err}"

    # Run ruff
    ruff_code, ruff_out, ruff_err = run_command(["ruff", "check", "."])
    if ruff_code != 0:
        return False, f"Ruff failed:\n{ruff_out}\n{ruff_err}"

    # Run mypy
    mypy_code, mypy_out, mypy_err = run_command(["mypy", "."])
    if mypy_code != 0:
        return False, f"Mypy failed:\n{mypy_out}\n{mypy_err}"

    return True, "All QA checks passed successfully."


def main() -> None:
    print("Starting QA Validation Loop...")
    issues = get_in_review_issues()
    if not issues:
        print("No issues in 'In Review' state.")
        return

    prs = get_open_prs()

    for issue in issues:
        issue_key = issue["key"]
        print(f"Processing issue: {issue_key}")

        # Find matching PR
        matching_pr = None
        for pr in prs:
            if issue_key in pr["headRefName"] or issue_key in pr["title"]:
                matching_pr = pr
                break

        if not matching_pr:
            print(f"No open PR found for {issue_key}")
            continue

        pr_number = str(matching_pr["number"])
        branch_name = matching_pr["headRefName"]
        print(f"Found PR #{pr_number} on branch {branch_name} for {issue_key}")

        # Fetch and checkout branch
        run_command(["git", "fetch", "origin", branch_name])
        run_command(["git", "checkout", branch_name])

        # Run tests
        passed, message = run_tests()

        if passed:
            print(f"QA Passed for {issue_key}")
            run_command(
                [
                    "gh",
                    "pr",
                    "review",
                    pr_number,
                    "--approve",
                    "-b",
                    "✅ QA Automation: All tests passed. Code looks good!",
                ]
            )
        else:
            print(f"QA Failed for {issue_key}")
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
            # Transition back to In Progress
            run_command(
                [
                    "python",
                    "scripts/jira_bridge.py",
                    "transition",
                    issue_key,
                    "In Progress",
                ]
            )

        # Checkout develop again
        run_command(["git", "checkout", "develop"])
        print("-" * 40)


if __name__ == "__main__":
    main()
