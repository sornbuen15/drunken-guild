from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "documents" / "concise-docs" / "SKILL.md"
REFERENCE = (
    REPO_ROOT
    / "skills"
    / "documents"
    / "concise-docs"
    / "references"
    / "pull-request.md"
)


def test_concise_docs_routes_pull_request_descriptions_to_reference() -> None:
    text = " ".join(SKILL.read_text(encoding="utf-8").split()).lower()

    assert "pull-request.md" in text
    assert "pull request" in text


def test_pull_request_reference_separates_task_change_reason_and_checks() -> None:
    assert REFERENCE.is_file(), "concise-docs must provide the referenced PR shape"
    text = REFERENCE.read_text(encoding="utf-8").lower()

    assert "## what" in text
    assert "## why" in text
    assert "## checklist" in text
    assert "task:" in text
    assert "actual result" in text
    assert "- [ ] <check run>" in text
    assert "- [x] <" not in text


def test_pull_request_reference_records_verified_ci_evidence() -> None:
    assert REFERENCE.is_file(), "concise-docs must provide the referenced PR shape"
    text = REFERENCE.read_text(encoding="utf-8").lower()

    assert "## evidence" in text
    for required_detail in (
        "profile and run id",
        "report sha and `overall` result",
        "ci verify path/report.json --json",
        "sha matches the branch head",
        "overall=pass",
        "skipped",
        "not_run",
        "local ci is unavailable",
    ):
        assert required_detail in text
