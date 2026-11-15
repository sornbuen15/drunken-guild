import json
from pathlib import Path
from typing import Any

import pytest

from core.ci_report import ReportError, load_report, revision_matches


def _report(**changes: Any) -> dict[str, Any]:
    report = {
        "contract_version": "0",
        "revision": {"sha": "abc123"},
        "checks": [
            {"id": "python-test", "required": True, "status": "pass"},
            {
                "id": "php-test",
                "required": True,
                "status": "skipped",
                "reason_code": "not_applicable",
                "reason": "stack not detected",
            },
        ],
        "overall": "pass",
    }
    report.update(changes)
    return report


def test_load_report_accepts_a_valid_report(tmp_path: Path) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report()), encoding="utf-8")

    evidence = load_report(path)

    assert evidence.sha == "abc123"
    assert evidence.overall == "pass"


@pytest.mark.parametrize(  # type: ignore[misc]
    "change",
    [
        {"contract_version": "1"},
        {"overall": "pass", "checks": []},
        {
            "overall": "pass",
            "checks": [{"id": "x", "required": True, "status": "fail"}],
        },
        {
            "overall": "pass",
            "checks": [{"id": "x", "required": True, "status": "not_run"}],
        },
    ],
)
def test_load_report_rejects_untrustworthy_results(
    tmp_path: Path, change: dict[str, Any]
) -> None:
    path = tmp_path / "report.json"
    path.write_text(json.dumps(_report(**change)), encoding="utf-8")

    with pytest.raises(ReportError):
        load_report(path)


def test_revision_matches_requires_the_exact_sha() -> None:
    assert revision_matches(_report(), "abc123")
    assert not revision_matches(_report(), "def456")
