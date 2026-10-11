# mypy: ignore-errors
"""DG-513. ``drunken-install context`` and ``drunken-install hook``.

The problem this answers: a real session did all the work itself and called no
skill or agent, because nothing at session start points it at the guild — a
project's own ``AGENTS.md`` may be absent (a fresh ``git worktree``), there is
no ``SessionStart`` hook installed anywhere, and the operator cannot see what
is installed. These two subcommands fix that without depending on either.

Explicit targets under ``tmp_path`` throughout; nothing here may reach the
real ``~/.claude`` or the real settings file. ``TestHook`` stubs
``resolve_hook_command`` everywhere it does not itself test resolution
(``TestResolveHookCommand``) or verification (``TestVerifyHookCommand``) —
this machine's own venv has a real ``drunken-install`` next to the test
runner, and a test asserting the exact command string must not depend on
that happening to be true.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core import install

BARE = install.GUILD_HOOK_FALLBACK  # "drunken-install context"


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


@pytest.fixture
def stub_resolve(monkeypatch):
    """Deterministic resolution: the bare command, resolved=True.

    Used by every ``TestHook`` case that is not itself testing resolution,
    so none of them depend on whether this machine happens to have a real
    ``drunken-install`` next to the interpreter running the suite.
    """
    monkeypatch.setattr(install, "resolve_hook_command", lambda: (BARE, True))


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

    def test_names_an_installed_skill(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(
            skills,
            "laravel-developer",
            "Use when building a Laravel feature end to end.",
        )
        payload = json.loads(install.context_json(skills, agents))
        text = payload["hookSpecificOutput"]["additionalContext"]
        assert "laravel-developer" in text

    def test_does_not_repeat_the_full_description(self, tmp_path: Path) -> None:
        """DG-513 item 5: names only — the real measurement was 3,624 chars
        of per-item descriptions, for one machine's worth of skills alone."""
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(
            skills,
            "laravel-developer",
            "A sentence that would not fit a names-only budget at all well.",
        )
        payload = json.loads(install.context_json(skills, agents))
        text = payload["hookSpecificOutput"]["additionalContext"]
        assert "would not fit a names-only budget" not in text

    def test_a_role_installed_as_both_a_skill_and_an_agent_is_named_once(
        self, tmp_path: Path
    ) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(skills, "worker-role", "The worker role skill.")
        make_agent(agents, "worker-role", "The worker agent adapter.")
        names = install._routing_names(skills, agents)
        assert names.count("worker-role") == 1

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
        make_agent(agents, "reviewer", "Reads a pull request before the Boss merges.")
        payload = json.loads(install.context_json(skills, agents))
        text = payload["hookSpecificOutput"]["additionalContext"]
        assert "reviewer" in text

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

    def test_falls_back_to_the_routing_rule_when_render_context_itself_raises(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """DG-513 item 2: the outer guard in ``context_json`` had no test at
        all — it only ever saw ``render_context``'s own internal guards."""
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"

        def boom(*_args, **_kwargs):
            raise ValueError("unexpected failure deep inside rendering")

        monkeypatch.setattr(install, "render_context", boom)
        text = install.context_json(skills, agents)
        payload = json.loads(text)
        assert (
            payload["hookSpecificOutput"]["additionalContext"] == install.ROUTING_RULE
        )

    def test_cli_context_still_exits_zero_when_render_context_raises(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        def boom(*_args, **_kwargs):
            raise RuntimeError("boom")

        monkeypatch.setattr(install, "render_context", boom)
        code = install.main(
            [
                "context",
                "--target",
                str(tmp_path / "skills"),
                "--agents-target",
                str(tmp_path / "agents"),
            ]
        )
        assert code == 0
        payload = json.loads(capsys.readouterr().out)
        assert (
            payload["hookSpecificOutput"]["additionalContext"] == install.ROUTING_RULE
        )

    def test_is_ascii_safe(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(skills, "alpha", "Uses an em dash \u2014 and other glyphs.")
        text = install.context_json(skills, agents)
        text.encode("ascii")  # raises if not ASCII-safe

    def test_contains_no_absolute_path(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        skills.mkdir()
        agents.mkdir()
        text = install.context_json(skills, agents)
        assert str(tmp_path) not in text

    def test_scrubs_a_windows_home_path_in_a_description(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(skills, "alpha", r"See C:\Users\alpha\notes for background.")
        text = install.render_context(skills, agents)
        assert "C:\\Users\\alpha" not in text
        assert r"\notes" not in text

    def test_scrubs_a_posix_home_path_in_a_description(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(skills, "beta", "See /home/alpha/notes for background.")
        text = install.render_context(skills, agents)
        assert "/home/alpha" not in text

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


class TestTruncateSentence:
    def test_the_marker_is_ascii_and_survives_the_scrub(self) -> None:
        """DG-513 item 4: the old U+2026 ellipsis was dropped by the ASCII
        scrub, so a truncated description read as merely cut off — no sign
        it had been. The fix has to actually survive ``_scrub``, not just
        look right before it runs."""
        long_description = "A" * 200
        truncated = install._truncate_sentence(long_description, limit=160)
        assert truncated.endswith("...")
        assert len(truncated) == 160
        scrubbed = install._scrub(truncated)
        assert scrubbed.endswith("...")

    def test_a_short_sentence_is_untouched(self) -> None:
        assert install._truncate_sentence("Short.", limit=160) == "Short."


class TestContextSizeBudget:
    def test_stays_under_the_cap_with_a_full_core_and_extras_install(
        self, tmp_path: Path
    ) -> None:
        """DG-513 item 5: 15 core skills + 31 extras, modelled on the real
        machine's install plus a second plugin's worth — the exact shape the
        review measured at 3,624 chars under the old per-item scheme."""
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        for i in range(15):
            make_skill(
                skills,
                f"core-skill-{i:02d}",
                "A description long enough to resemble a real one, with detail.",
            )
        for i in range(31):
            make_skill(
                skills,
                f"extra-skill-{i:02d}",
                "Another realistic-length description for an optional extra.",
            )
        for i in range(3):
            make_agent(
                agents, f"role-{i}", "An agent adapter description, also realistic."
            )
        text = install.render_context(skills, agents)
        assert len(text) <= install.CONTEXT_CHAR_LIMIT
        assert install.ROUTING_RULE in text

    def test_the_routing_rule_is_never_cut_even_with_hundreds_of_names(
        self, tmp_path: Path
    ) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        for i in range(400):
            make_skill(skills, f"skill-{i:04d}", "x")
        text = install.render_context(skills, agents)
        assert install.ROUTING_RULE in text
        assert len(text) <= install.CONTEXT_CHAR_LIMIT
        assert "more, see drunken-install status" in text


class TestHook:
    def test_plan_reports_add_when_settings_file_is_absent(
        self, tmp_path: Path, stub_resolve
    ) -> None:
        settings_path = tmp_path / "settings.json"
        plan = install.plan_hook(settings_path, remove=False)
        assert plan.action == "add"

    def test_apply_writes_a_session_start_hook_entry(
        self, tmp_path: Path, stub_resolve
    ) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_hook(settings_path, apply=True)
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        commands = [
            h.get("command")
            for entry in data["hooks"]["SessionStart"]
            for h in entry.get("hooks", [])
        ]
        assert BARE in commands

    def test_preserves_existing_keys_and_other_hooks(
        self, tmp_path: Path, stub_resolve
    ) -> None:
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

    def test_is_idempotent(self, tmp_path: Path, stub_resolve) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_hook(settings_path, apply=True)
        first = settings_path.read_text(encoding="utf-8")
        install.apply_hook(settings_path, apply=True)
        second = settings_path.read_text(encoding="utf-8")
        assert first == second

    def test_is_idempotent_even_when_the_resolved_path_changes_between_runs(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """DG-513 item 1: the exact absolute path can differ run to run (a
        reinstall, a different venv) — detection must not key off the exact
        string or every later run would add a second entry forever."""
        settings_path = tmp_path / "settings.json"
        monkeypatch.setattr(
            install,
            "resolve_hook_command",
            lambda: (r'"C:\old\drunken-install.exe" context', True),
        )
        install.apply_hook(settings_path, apply=True)
        monkeypatch.setattr(
            install,
            "resolve_hook_command",
            lambda: (r'"D:\new\drunken-install.exe" context', True),
        )
        plan = install.plan_hook(settings_path)
        assert plan.action == "already-present"
        install.apply_hook(settings_path, apply=True)
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert len(data["hooks"]["SessionStart"]) == 1

    def test_plan_only_does_not_write(self, tmp_path: Path, stub_resolve) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_hook(settings_path, apply=False)
        assert not settings_path.exists()

    def test_remove_undoes_exactly_the_guild_entry(
        self, tmp_path: Path, stub_resolve
    ) -> None:
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
        assert BARE not in commands
        assert "echo other" in commands

    def test_refuses_on_invalid_json(self, tmp_path: Path, stub_resolve) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text("{ not json", encoding="utf-8")
        with pytest.raises(install.InstallRefusedError):
            install.apply_hook(settings_path, apply=True)
        assert settings_path.read_text(encoding="utf-8") == "{ not json"

    def test_refuses_when_hooks_key_is_not_an_object(
        self, tmp_path: Path, stub_resolve
    ) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"hooks": "nope"}), encoding="utf-8")
        with pytest.raises(install.InstallRefusedError):
            install.apply_hook(settings_path, apply=True)

    def test_backs_up_the_original_before_the_first_change(
        self, tmp_path: Path, stub_resolve
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

    def test_aborts_when_the_file_changes_between_read_and_write(
        self, tmp_path: Path, stub_resolve, monkeypatch
    ) -> None:
        """DG-513 item 6: a second writer between the first read and the
        atomic replace must not be silently overwritten."""
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"permissions": {}}), encoding="utf-8")

        raced_content = json.dumps({"permissions": {"raced": True}})

        def racing_merge(settings, command):
            # Simulates another process writing to the file in the window
            # between apply_hook's first read and its atomic write.
            settings_path.write_text(raced_content, encoding="utf-8")
            return {
                **settings,
                "hooks": {
                    "SessionStart": [
                        {
                            "matcher": "",
                            "hooks": [{"type": "command", "command": command}],
                        }
                    ]
                },
            }

        monkeypatch.setattr(install, "_merge_add", racing_merge)
        with pytest.raises(install.InstallRefusedError):
            install.apply_hook(settings_path, apply=True)
        assert settings_path.read_text(encoding="utf-8") == raced_content

    def test_cli_hook_apply_then_plan_is_a_noop(
        self, tmp_path: Path, stub_resolve, capsys
    ) -> None:
        settings_path = tmp_path / "settings.json"
        code = install.main(["hook", "--settings", str(settings_path), "--apply"])
        assert code == 0
        capsys.readouterr()
        code = install.main(["hook", "--settings", str(settings_path)])
        assert code == 0
        out = capsys.readouterr().out
        assert "already" in out.lower() or "present" in out.lower()


class TestResolveHookCommand:
    def test_prefers_drunken_install_on_path(self, monkeypatch) -> None:
        monkeypatch.setattr(
            install.shutil, "which", lambda name: r"C:\bin\drunken-install.exe"
        )
        command, resolved = install.resolve_hook_command()
        assert resolved is True
        assert r"C:\bin\drunken-install.exe" in command
        assert command.endswith("context")

    def test_quotes_a_path_containing_a_space_on_windows(self, monkeypatch) -> None:
        monkeypatch.setattr(install, "os", install.os)
        monkeypatch.setattr(install.os, "name", "nt")
        monkeypatch.setattr(
            install.shutil,
            "which",
            lambda name: r"C:\Program Files\guild\drunken-install.exe",
        )
        command, resolved = install.resolve_hook_command()
        assert resolved is True
        assert command.startswith('"C:\\Program Files\\guild\\drunken-install.exe"')

    def test_falls_back_to_a_sibling_of_the_running_interpreter(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(install.shutil, "which", lambda name: None)
        fake_python_dir = tmp_path
        sibling = fake_python_dir / (
            "drunken-install.exe" if install.os.name == "nt" else "drunken-install"
        )
        sibling.write_bytes(b"")
        monkeypatch.setattr(
            install.sys, "executable", str(fake_python_dir / "python.exe")
        )
        command, resolved = install.resolve_hook_command()
        assert resolved is True
        assert "drunken-install" in command

    def test_falls_back_to_the_bare_command_when_nothing_resolves(
        self, monkeypatch, tmp_path
    ) -> None:
        monkeypatch.setattr(install.shutil, "which", lambda name: None)
        monkeypatch.setattr(install.sys, "executable", str(tmp_path / "python.exe"))
        command, resolved = install.resolve_hook_command()
        assert resolved is False
        assert command == BARE

    def test_an_unresolved_plan_says_so_in_the_plan_output(
        self, tmp_path, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(install, "resolve_hook_command", lambda: (BARE, False))
        settings_path = tmp_path / "settings.json"
        install.main(["hook", "--settings", str(settings_path)])
        out = capsys.readouterr().out
        assert "WARNING" in out
        assert "not on PATH" in out or "fails silently" in out


class TestVerifyHookCommand:
    def test_ok_when_the_command_prints_the_expected_json(self) -> None:
        script = (
            "import json,sys;"
            "print(json.dumps({'hookSpecificOutput': "
            "{'hookEventName': 'SessionStart', 'additionalContext': 'x'}}))"
        )
        command = f'"{sys.executable}" -c "{script}"'
        ok, reason = install.verify_hook_command(command)
        assert ok is True
        assert reason == ""

    def test_not_found_when_the_program_does_not_exist(self, tmp_path) -> None:
        missing = tmp_path / "does-not-exist-drunken-install.exe"
        ok, reason = install.verify_hook_command(f'"{missing}" context')
        assert ok is False
        assert "not found" in reason

    def test_bad_exit_code_when_the_version_is_too_old(self) -> None:
        script = "import sys; sys.exit(2)"
        command = f'"{sys.executable}" -c "{script}"'
        ok, reason = install.verify_hook_command(command)
        assert ok is False
        assert "exited with code 2" in reason

    def test_bad_output_when_it_exits_zero_but_prints_nothing_useful(self) -> None:
        script = "print('not json at all')"
        command = f'"{sys.executable}" -c "{script}"'
        ok, reason = install.verify_hook_command(command)
        assert ok is False
        assert "did not print" in reason

    def test_times_out_on_a_hanging_command(self) -> None:
        script = "import time; time.sleep(5)"
        command = f'"{sys.executable}" -c "{script}"'
        ok, reason = install.verify_hook_command(command, timeout=0.2)
        assert ok is False
        assert "did not finish" in reason

    def test_empty_command_is_reported_rather_than_run(self) -> None:
        ok, reason = install.verify_hook_command("")
        assert ok is False
        assert "no command" in reason
