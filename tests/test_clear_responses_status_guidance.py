"""REQ-031: work-status guidance must be concrete and evidence-bound."""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
SKILL = REPO_ROOT / "skills" / "documents" / "clear-responses" / "SKILL.md"


def test_work_status_guidance_names_state_and_next_action() -> None:
    text = " ".join(SKILL.read_text(encoding="utf-8").split())

    assert (
        "State completed, active, blocked, or idle only as the evidence supports"
        in text
    )
    assert "include the next action when work remains" in text


def test_uncommitted_files_do_not_claim_background_work() -> None:
    text = " ".join(SKILL.read_text(encoding="utf-8").split())

    assert (
        "A branch with uncommitted changes proves changes exist, not that work is"
        in text
    )
    assert "running in the background" in text


def test_skill_links_to_manual_status_scenarios() -> None:
    text = " ".join(SKILL.read_text(encoding="utf-8").split())

    assert "examples/communication/status-updates.md" in text
