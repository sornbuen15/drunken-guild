"""The build handoff keeps the local CI result tied to the pushed PR head."""

from pathlib import Path

BUILD = (
    Path(__file__).resolve().parent.parent / "skills" / "flow" / "build" / "SKILL.md"
)
HANDOFF = BUILD.parent / "references" / "local-ci-handoff.md"


def test_build_requires_current_pushed_head_before_ready_pr() -> None:
    assert "references/local-ci-handoff.md" in BUILD.read_text(encoding="utf-8")
    text = " ".join(HANDOFF.read_text(encoding="utf-8").lower().split())

    required_in_order = (
        "latest pr base branch",
        "push the branch",
        "ci check --profile full",
        "overall=pass",
        "ci verify <report.json> --json",
        "only after verification, open a pr",
    )
    positions = [text.index(fragment) for fragment in required_in_order]
    assert positions == sorted(positions)
    assert "pushed head sha" in text
    assert "report sha" in text and "current branch head" in text


def test_build_requires_recheck_and_stops_when_ci_unavailable() -> None:
    text = " ".join(HANDOFF.read_text(encoding="utf-8").lower().split())

    assert "fix, commit, push" in text
    assert "run `ci check --profile full` again" in text
    assert "never open a pr on a failing or stale report" in text
    assert "do not open the pr as ready" in text
    assert "`not_run`" in text
    assert "observed reason" in text
    assert "boss" in text


def test_build_does_not_require_local_ci_when_project_has_not_selected_it() -> None:
    text = " ".join(HANDOFF.read_text(encoding="utf-8").lower().split())

    assert "project has not selected local ci" in text
    assert "normal pr workflow" in text
    assert "no local ci report is required" in text
    assert "selected local ci is unavailable" in text
