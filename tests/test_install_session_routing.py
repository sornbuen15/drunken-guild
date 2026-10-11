# mypy: ignore-errors
"""DG-session-routing. ``drunken-install context`` and ``drunken-install hook``.

The problem this answers: a real session did all the work itself and called no
skill or agent, because nothing at session start points it at the guild — a
project's own ``AGENTS.md`` may be absent (a fresh ``git worktree``), there is
no ``SessionStart`` hook installed anywhere, and the operator cannot see what
is installed. These two subcommands fix that without depending on either.

Explicit targets under ``tmp_path`` throughout; nothing here may reach the
real ``~/.claude`` or the real settings file.
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from core import install


def make_skill(root: Path, name: str, description: str) -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: >\n  {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def make_agent(root: Path, name: str, description: str) -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nbody\n",
        encoding="utf-8",
    )


class TestContext:
    def test_prints_one_json_object_with_the_hook_shape(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        skills.mkdir()
        agents.mkdir()
        text = install.context_json(skills, agents)
        payload = json.loads(text)
        assert payload["hookSpecificOutput"]["hookEventName"] == "SessionStart"
        assert "additionalContext" in payload["hookSpecificOutput"]

    def test_names_an_installed_skill_by_its_first_sentence(
        self, tmp_path: Path
    ) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(
            skills,
            "laravel-developer",
            "Use when building a Laravel feature end to end. Longer detail follows here.",
        )
        payload = json.loads(install.context_json(skills, agents))
        text = payload["hookSpecificOutput"]["additionalContext"]
        assert "laravel-developer" in text
        assert "Use when building a Laravel feature end to end." in text
        assert "Longer detail follows here" not in text

    def test_omits_a_skill_that_is_not_installed(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        skills.mkdir()
        agents.mkdir()
        payload = json.loads(install.context_json(skills, agents))
        text = payload["hookSpecificOutput"]["additionalContext"]
        assert "laravel-developer" not in text

    def test_names_an_installed_agent(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        skills.mkdir()
        make_agent(agents, "worker", "Implements exactly one approved task.")
        payload = json.loads(install.context_json(skills, agents))
        text = payload["hookSpecificOutput"]["additionalContext"]
        assert "worker" in text

    def test_carries_the_routing_rule_even_with_nothing_installed(
        self, tmp_path: Path
    ) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        payload = json.loads(install.context_json(skills, agents))
        text = payload["hookSpecificOutput"]["additionalContext"]
        assert "/build" in text
        assert "worker" in text.lower() or "Skill or Agent tool" in text

    def test_never_raises_on_a_broken_skill_file(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        broken = skills / "broken"
        broken.mkdir(parents=True)
        (broken / "SKILL.md").write_bytes(b"\xff\xfe not valid utf-8 \x00")
        text = install.context_json(skills, agents)
        payload = json.loads(text)
        assert "additionalContext" in payload["hookSpecificOutput"]

    def test_is_ascii_safe(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(skills, "alpha", "Uses an em dash — and other glyphs.")
        text = install.context_json(skills, agents)
        text.encode("ascii")  # raises if not ASCII-safe

    def test_contains_no_absolute_path(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        skills.mkdir()
        agents.mkdir()
        text = install.context_json(skills, agents)
        assert str(tmp_path) not in text

    def test_cli_context_exits_zero_and_prints_json(
        self, tmp_path: Path, capsys
    ) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        skills.mkdir()
        agents.mkdir()
        code = install.main(
            ["context", "--target", str(skills), "--agents-target", str(agents)]
        )
        assert code == 0
        out = capsys.readouterr().out
        json.loads(out)


class TestHook:
    def test_plan_reports_add_when_settings_file_is_absent(
        self, tmp_path: Path
    ) -> None:
        settings_path = tmp_path / "settings.json"
        plan = install.plan_hook(settings_path, remove=False)
        assert plan.action == "add"

    def test_apply_writes_a_session_start_hook_entry(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_hook(settings_path, apply=True)
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        commands = [
            h.get("command")
            for entry in data["hooks"]["SessionStart"]
            for h in entry.get("hooks", [])
        ]
        assert "drunken-install context" in commands

    def test_preserves_existing_keys_and_other_hooks(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "permissions": {"deny": ["Bash(rm -rf:*)"]},
                    "hooks": {
                        "PreToolUse": [
                            {
                                "matcher": "*",
                                "hooks": [{"type": "command", "command": "echo hi"}],
                            }
                        ]
                    },
                }
            ),
            encoding="utf-8",
        )
        install.apply_hook(settings_path, apply=True)
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert data["permissions"]["deny"] == ["Bash(rm -rf:*)"]
        assert data["hooks"]["PreToolUse"][0]["hooks"][0]["command"] == "echo hi"
        assert "SessionStart" in data["hooks"]

    def test_is_idempotent(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_hook(settings_path, apply=True)
        first = settings_path.read_text(encoding="utf-8")
        install.apply_hook(settings_path, apply=True)
        second = settings_path.read_text(encoding="utf-8")
        assert first == second

    def test_plan_only_does_not_write(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_hook(settings_path, apply=False)
        assert not settings_path.exists()

    def test_remove_undoes_exactly_the_guild_entry(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "SessionStart": [
                            {
                                "matcher": "",
                                "hooks": [{"type": "command", "command": "echo other"}],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        install.apply_hook(settings_path, apply=True)
        install.apply_hook(settings_path, apply=True, remove=True)
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        commands = [
            h.get("command")
            for entry in data["hooks"]["SessionStart"]
            for h in entry.get("hooks", [])
        ]
        assert "drunken-install context" not in commands
        assert "echo other" in commands

    def test_refuses_on_invalid_json(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(install.InstallRefusedError):
            install.apply_hook(settings_path, apply=True)
        assert settings_path.read_text(encoding="utf-8") == "{ not json"

    def test_refuses_when_hooks_key_is_not_an_object(self, tmp_path: Path) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"hooks": "nope"}), encoding="utf-8")
        with pytest.raises(install.InstallRefusedError):
            install.apply_hook(settings_path, apply=True)

    def test_backs_up_the_original_before_the_first_change(
        self, tmp_path: Path
    ) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps({"permissions": {"deny": []}}), encoding="utf-8"
        )
        original = settings_path.read_text(encoding="utf-8")
        install.apply_hook(settings_path, apply=True)
        backups = list(tmp_path.glob("settings.json.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == original

    def test_cli_hook_apply_then_plan_is_a_noop(self, tmp_path: Path, capsys) -> None:
        settings_path = tmp_path / "settings.json"
        code = install.main(["hook", "--settings", str(settings_path), "--apply"])
        assert code == 0
        capsys.readouterr()
        code = install.main(["hook", "--settings", str(settings_path)])
        assert code == 0
        out = capsys.readouterr().out
        assert "already" in out.lower() or "present" in out.lower()
