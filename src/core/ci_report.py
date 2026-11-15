"""Read and validate the vendor-neutral local-CI report contract."""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any


class ReportError(ValueError):
    """A report is missing trustworthy evidence or violates contract version 0."""


@dataclass(frozen=True)
class ReportEvidence:
    sha: str
    overall: str
    profile: str | None


def _derived_overall(checks: list[dict[str, Any]]) -> str:
    required = [check for check in checks if check.get("required", True)]
    if not required:
        return "incomplete"
    if any(check.get("status") in {"fail", "timeout", "error"} for check in required):
        return "fail"
    if any(check.get("status") in {"not_run", "skipped"} for check in required):
        if all(
            check.get("status") == "skipped"
            and check.get("reason_code") == "not_applicable"
            for check in required
            if check.get("status") == "skipped"
        ) and any(check.get("status") == "pass" for check in required):
            return "pass"
        return "incomplete"
    return (
        "pass"
        if any(check.get("status") == "pass" for check in required)
        else "incomplete"
    )


def load_report(path: str | Path) -> ReportEvidence:
    """Load one report and reject results that cannot support a handoff."""
    try:
        report = json.loads(Path(path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ReportError(f"cannot read report: {exc}") from exc
    if not isinstance(report, dict) or report.get("contract_version") != "0":
        raise ReportError("unsupported or missing report contract version")
    revision = report.get("revision")
    sha = revision.get("sha") if isinstance(revision, dict) else None
    checks = report.get("checks")
    if not isinstance(sha, str) or not sha or not isinstance(checks, list):
        raise ReportError("report needs revision.sha and checks")
    for check in checks:
        if not isinstance(check, dict) or not check.get("id") or "status" not in check:
            raise ReportError("each check needs an id and status")
        if check["status"] in {"skipped", "not_run"} and not (
            check.get("reason_code") and check.get("reason")
        ):
            raise ReportError("skipped and not_run checks need reason evidence")
    derived = _derived_overall(checks)
    if report.get("overall") != derived:
        raise ReportError(f"overall disagrees with checks: expected {derived}")
    return ReportEvidence(sha=sha, overall=derived, profile=report.get("profile"))


def revision_matches(report: dict[str, Any], expected_sha: str) -> bool:
    revision = report.get("revision")
    return isinstance(revision, dict) and revision.get("sha") == expected_sha
