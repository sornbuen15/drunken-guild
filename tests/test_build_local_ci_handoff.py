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
        "push it",
        "ci check --profile full",
        "once `overall=pass`, run",
        "ci verify <report.json> --json",
        "only after windows verification confirms the current pushed sha, open the pr on macos",
    )
    positions = [text.index(fragment) for fragment in required_in_order]
    assert positions == sorted(positions)
    assert "pushed head sha" in text
    assert "report sha" in text and "current pushed branch head" in text


def test_build_requires_recheck_and_stops_when_ci_unavailable() -> None:
    text = " ".join(HANDOFF.read_text(encoding="utf-8").lower().split())

    assert "fix the issue on macos, push the updated branch" in text
    assert "repeat the windows check on the new pushed head sha" in text
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
    assert "windows-side ci is unavailable" in text


def test_local_ci_handoff_names_windows_check_and_macos_pr_owner() -> None:
    text = " ".join(HANDOFF.read_text(encoding="utf-8").lower().split())

    assert "macos" in text and "windows" in text
    assert "windows-side" in text
    assert "ci check --profile full" in text
    assert "ci verify <report.json> --json" in text
    assert "pushed head sha" in text
    assert "open the pr on macos" in text
    assert (
        text.index("on windows, fetch")
        < text.index("only after windows verification confirms the current pushed sha")
        < text.index("open the pr on macos")
    )
    assert "if windows-side ci is unavailable" in text
    assert "`not_run`" in text
