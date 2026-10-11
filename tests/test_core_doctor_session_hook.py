# mypy: ignore-errors
"""``routes.session_hook`` — DG-session-routing.

Whether the SessionStart hook that runs ``drunken-install context`` is
present in the user's own Claude settings file, so a session is routed to the
guild's skills and agents even when a project's ``AGENTS.md`` is absent (a
fresh ``git worktree``) and nobody remembers to ask.
"""

from __future__ import annotations

import json

from core import doctor, install


def _named(report, name):
    return next((c for c in report.checks if c.name == name), None)


class TestSessionHookCheck:
    def test_warns_with_the_exact_fix_command_when_absent(self, tmp_path) -> None:
        settings_path = tmp_path / "settings.json"
        report = doctor.Report()
        doctor._check_session_hook(report, settings_path)
        check = _named(report, "routes.session_hook")
        assert check.status == "warn"
        assert check.remediation == "drunken-install hook --apply"

    def test_is_ok_when_present(self, tmp_path) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_hook(settings_path, apply=True)
        report = doctor.Report()
        doctor._check_session_hook(report, settings_path)
        check = _named(report, "routes.session_hook")
        assert check.status == "ok"

    def test_skips_with_a_reason_when_settings_cannot_be_read(self, tmp_path) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{ not json", encoding="utf-8")
        report = doctor.Report()
        doctor._check_session_hook(report, settings_path)
        check = _named(report, "routes.session_hook")
        assert check.status == "skip"
        assert str(settings_path) in check.detail

    def test_warns_when_present_file_has_hooks_but_not_ours(self, tmp_path) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps({"hooks": {"SessionStart": [{"matcher": "", "hooks": []}]}}),
            encoding="utf-8",
        )
        report = doctor.Report()
        doctor._check_session_hook(report, settings_path)
        check = _named(report, "routes.session_hook")
        assert check.status == "warn"
