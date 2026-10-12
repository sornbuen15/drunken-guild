# mypy: ignore-errors
"""DG-515. ``drunken-install route`` — a ``UserPromptSubmit`` hook that reads a prompt and names
the skills/agents a worker should call before doing the work, in Thai and English.

The problem this answers (FINDING on DG-515): a ``SessionStart`` hook only speaks once, at the
top of a session; a later prompt on an existing project gets no routing nudge at all and made 0
Skill calls in the experiment that found this. This covers the keyword table, the installed-only
filter, the 600-character cap, the merged ``UserPromptSubmit`` hook entry (same safety as the
``SessionStart`` merge DG-513 built), and the doctor check that it actually runs.

Fixtures build only the exact skill folders a case needs, the same style
``test_install_session_routing.py`` uses — nothing here reaches the real ``~/.claude``.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from core import install

BARE_ROUTE = install.GUILD_ROUTE_FALLBACK  # "drunken-install route"


def make_skill(root: Path, name: str, description: str = "A skill.") -> None:
    folder = root / name
    folder.mkdir(parents=True)
    (folder / "SKILL.md").write_text(
        f"---\nname: {name}\ndescription: >\n  {description}\n---\n\n# {name}\n",
        encoding="utf-8",
    )


def make_agent(root: Path, name: str, description: str = "An agent.") -> None:
    root.mkdir(parents=True, exist_ok=True)
    (root / f"{name}.md").write_text(
        f"---\nname: {name}\ndescription: {description}\n---\n\nbody\n",
        encoding="utf-8",
    )


@pytest.fixture
def stub_resolve_route(monkeypatch):
    monkeypatch.setattr(
        install, "resolve_route_hook_command", lambda: (BARE_ROUTE, True)
    )


# A prompt per SDLC step this ticket's keyword table must cover, Thai and English, and the
# names the data file maps that step to (see src/core/data/route_keywords.json).
SDLC_CASES = [
    (
        "requirements",
        "en",
        "What is the scope for this new requirement?",
        ["prd", "clarify"],
    ),
    ("requirements", "th", "ช่วยเขียนความต้องการและขอบเขตงานให้หน่อย", ["prd", "clarify"]),
    ("design", "en", "Help me design the architecture for this service.", ["ddd"]),
    ("design", "th", "ช่วยออกแบบระบบและสถาปัตยกรรมให้หน่อย", ["ddd"]),
    ("build", "en", "Please implement this new feature.", ["build", "worker"]),
    ("build", "th", "ช่วยพัฒนาฟีเจอร์นี้ให้หน่อย", ["build", "worker"]),
    ("tests", "en", "Add a unit test for this function.", ["build"]),
    ("tests", "th", "ช่วยเขียนทดสอบให้หน่อย", ["build"]),
    (
        "bugfix",
        "en",
        "There is a bug, it is broken, please fix it.",
        ["build", "worker"],
    ),
    ("bugfix", "th", "เจอบักแก้บักให้หน่อย", ["build", "worker"]),
    ("review", "en", "Please review this pull request.", ["reviewer"]),
    ("review", "th", "ช่วยรีวิวโค้ดให้หน่อย", ["reviewer"]),
    (
        "security",
        "en",
        "Check this endpoint's security and password handling.",
        ["reviewer"],
    ),
    ("security", "th", "ช่วยตรวจความปลอดภัยและรหัสผ่านให้หน่อย", ["reviewer"]),
    ("ui_ux", "en", "Design the UI for this screen.", ["build"]),
    ("ui_ux", "th", "ช่วยออกแบบหน้าจอและฟอร์มให้หน่อย", ["build"]),
    ("git", "en", "Help me with this git branch and git commit.", ["git-workflow"]),
    ("git", "th", "ช่วยทำกิตแบรนช์และกิตคอมมิตให้หน่อย", ["git-workflow"]),
    ("deploy", "en", "We need to deploy this to production.", ["ask-boss"]),
    ("deploy", "th", "ช่วยดีพลอยขึ้นโปรดักชันให้หน่อย", ["ask-boss"]),
    ("docs", "en", "Please write the documentation for this.", ["project-docs"]),
    ("docs", "th", "ช่วยเขียนเอกสารให้หน่อย", ["project-docs"]),
]


@pytest.fixture
def core_skills(tmp_path: Path) -> tuple[Path, Path]:
    """Only the skills this ticket's own data file ever names, nothing from ``universal-*``
    or ``secure-by-design`` (those are optional ``drunken-extras`` skills) — proves the
    installed-only filter actually filters, not merely happens to pass."""
    skills = tmp_path / "skills"
    agents = tmp_path / "agents"
    for name in (
        "prd",
        "clarify",
        "ddd",
        "build",
        "reviewer",
        "git-workflow",
        "ask-boss",
        "project-docs",
        "worker",
    ):
        make_skill(skills, name)
    agents.mkdir()
    return skills, agents


@pytest.fixture
def extras_skills(tmp_path: Path) -> tuple[Path, Path]:
    """Core skills plus the ``drunken-extras`` names the widened table can also name — a temp
    HOME with extras installed, the shape the lead's follow-up measured against and found the
    core-only matrix run (DG-515's first pass) was not representative of."""
    skills = tmp_path / "skills"
    agents = tmp_path / "agents"
    for name in (
        "prd",
        "clarify",
        "ddd",
        "build",
        "reviewer",
        "git-workflow",
        "ask-boss",
        "project-docs",
        "worker",
        "breakdown",
        "universal-ui",
        "universal-ux",
        "secure-by-design",
        "test-strategy",
        "test-architecture",
    ):
        make_skill(skills, name)
    make_agent(agents, "security-engineer")
    return skills, agents


# DG-515 follow-up: realistic prompts the lead actually ran against a built exe, Thai, English
# and mixed -- the exact shape the narrow first-pass table missed.
REALISTIC_POSITIVE_CASES = [
    ("ui_ux", "th", "ทำหน้า login ให้หน่อย", ["universal-ui", "universal-ux"]),
    ("ui_ux", "th", "เพิ่มฟอร์มสมัครสมาชิก", ["universal-ui", "universal-ux"]),
    (
        "bugfix",
        "th",
        "ฟังก์ชัน price คิดเงินผิดเมื่อ qty เป็น 0 ช่วยแก้ให้หน่อย",
        ["build", "worker"],
    ),
    (
        "security",
        "mixed",
        "เพิ่ม endpoint รับ token แล้วเช็กสิทธิ์",
        ["reviewer", "secure-by-design", "security-engineer"],
    ),
    (
        "tests",
        "mixed",
        "เพิ่มฟังก์ชันคำนวณส่วนลดพร้อมเทส",
        ["build", "test-strategy", "test-architecture"],
    ),
    ("review", "mixed", "review PR นี้ให้หน่อย", ["reviewer"]),
    ("deploy", "mixed", "deploy ขึ้น staging", ["ask-boss"]),
    ("docs", "mixed", "เขียน README", ["project-docs"]),
    # Tone-mark variants of the already-covered bugfix case (DG-515 follow-up item 3): a real
    # user spells "bug"/"fix" with or without the tone mark interchangeably.
    ("bugfix", "th", "เจอบั๊กแล้ว ช่วยแก้บั๊กให้หน่อย", ["build", "worker"]),
    # Planning/breakdown, the group the lead listed without naming a category explicitly.
    ("requirements", "th", "ช่วยวางแผนและแตกงานโปรเจกต์นี้หน่อย", ["prd", "breakdown"]),
    (
        "requirements",
        "en",
        "Help me plan and break down this project.",
        ["prd", "breakdown"],
    ),
]

# DG-515 follow-up item 1: at least 12 prompts that must print nothing -- chit-chat, a request
# to explain existing code, anything with no SDLC-step keyword at all.
NEGATIVE_PROMPTS = [
    "สวัสดีครับ วันนี้อากาศเป็นไง",
    "คุณเป็น AI ตัวไหน",
    "เล่าเรื่องตลกให้ฟังหน่อย",
    "วันนี้วันอะไร",
    "มื้อเที่ยงกินอะไรดี",
    "เพลงนี้ชื่ออะไร",
    "อธิบายโค้ดนี้ให้หน่อย",
    "สรุปบทความนี้ให้หน่อย",
    "ขอสูตรทำขนมหน่อย",
    "แปลประโยคนี้เป็นภาษาไทย",
    "เล่นเกมอะไรดีคืนนี้",
    "I'm just saying hello, how are you today?",
    "What's your favorite color?",
    # DG-515 second review round: bare "error" and bare "api" were both false-positiving on
    # a question *about* the word, not a request to do anything with it.
    "What does this error message mean: KeyError?",
    "What does API stand for?",
]


class TestRealisticPromptsFromTheLeadsFollowUp:
    """DG-515 follow-up: the first-pass table was measured too narrow on real prompts against
    a temp HOME with extras installed -- these are exactly the prompts that were checked."""

    @pytest.mark.parametrize(
        "category, lang, prompt, expected",
        REALISTIC_POSITIVE_CASES,
        ids=[
            f"{c}-{lang}-{i}"
            for i, (c, lang, _p, _e) in enumerate(REALISTIC_POSITIVE_CASES)
        ],
    )
    def test_realistic_prompt_names_the_expected_skills(
        self, extras_skills, category, lang, prompt, expected
    ) -> None:
        skills, agents = extras_skills
        text = install.route_text(prompt, skills, agents)
        for name in expected:
            assert name in text, f"{category}/{lang}: expected {name!r} in {text!r}"

    @pytest.mark.parametrize(
        "prompt", NEGATIVE_PROMPTS, ids=range(len(NEGATIVE_PROMPTS))
    )
    def test_negative_prompt_prints_nothing(self, extras_skills, prompt) -> None:
        skills, agents = extras_skills
        assert install.route_text(prompt, skills, agents) == ""


class TestKeywordMatchingRules:
    """DG-515 follow-up item 3: a short Latin token ("ui", "ux", "api", "pr") must match on
    word boundaries only -- the first-pass table matched "ui" as a bare substring, so
    "please build this feature" and "this field is required" both silently routed to
    universal-ui/universal-ux too. Thai keywords stay substring matches (no word-boundary
    convention in Thai orthography), and a tone-mark variant must compare equal."""

    def test_build_does_not_trigger_ui(self, extras_skills) -> None:
        skills, agents = extras_skills
        text = install.route_text("please build this feature", skills, agents)
        assert "universal-ui" not in text
        assert "universal-ux" not in text

    def test_required_does_not_trigger_ui(self, extras_skills) -> None:
        skills, agents = extras_skills
        text = install.route_text("this field is required", skills, agents)
        assert text == ""

    def test_print_does_not_trigger_review_via_pr(self, extras_skills) -> None:
        skills, agents = extras_skills
        text = install.route_text("please print the report", skills, agents)
        assert "reviewer" not in text

    def test_rapid_does_not_trigger_security_via_api(self, extras_skills) -> None:
        skills, agents = extras_skills
        text = install.route_text("let's take a rapid approach here", skills, agents)
        assert "secure-by-design" not in text
        assert "security-engineer" not in text

    def test_a_whole_word_ui_still_matches(self, extras_skills) -> None:
        skills, agents = extras_skills
        text = install.route_text("please fix the UI on this page", skills, agents)
        assert "universal-ui" in text

    def test_a_whole_word_pr_still_matches(self, extras_skills) -> None:
        skills, agents = extras_skills
        text = install.route_text("please merge this PR", skills, agents)
        assert "reviewer" in text

    def test_tone_mark_variant_of_a_bug_keyword_matches(self, extras_skills) -> None:
        skills, agents = extras_skills
        text = install.route_text("เจอบั๊กแล้ว", skills, agents)
        assert "build" in text


class TestRouteTextSdlcCoverage:
    @pytest.mark.parametrize(
        "category, lang, prompt, expected",
        SDLC_CASES,
        ids=[f"{c}-{lang}" for c, lang, _p, _e in SDLC_CASES],
    )
    def test_each_sdlc_step_in_each_language_names_the_expected_skills(
        self, core_skills, category, lang, prompt, expected
    ) -> None:
        skills, agents = core_skills
        text = install.route_text(prompt, skills, agents)
        for name in expected:
            assert name in text, f"{category}/{lang}: expected {name!r} in {text!r}"

    def test_an_unmatched_prompt_prints_nothing(self, core_skills) -> None:
        skills, agents = core_skills
        text = install.route_text("let's chat about the weather today", skills, agents)
        assert text == ""

    def test_a_vague_idea_prompt_prints_nothing(self, core_skills) -> None:
        """FINDING's own baseline case: a vague new-project idea must not be forced into an
        SDLC-step bucket it was never meant for."""
        skills, agents = core_skills
        text = install.route_text(
            "I have an idea for an app, not sure where to start", skills, agents
        )
        assert text == ""


class TestRouteInstalledOnlyFilter:
    def test_never_names_a_skill_that_is_not_installed(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        skills.mkdir()
        agents.mkdir()
        # design maps to ddd/system-design-rules/clean-architecture, none installed here.
        text = install.route_text("help me design the architecture", skills, agents)
        assert text == ""
        assert "ddd" not in text
        assert "system-design-rules" not in text

    def test_names_only_the_subset_that_is_installed(self, tmp_path: Path) -> None:
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(skills, "ddd")
        agents.mkdir()
        text = install.route_text(
            "help me design the architecture and data model", skills, agents
        )
        assert "ddd" in text
        assert "system-design-rules" not in text
        assert "clean-architecture" not in text

    def test_does_not_enumerate_every_installed_skill(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        """DG-515 review round 2: ``route_text`` used to call ``_routing_names`` on every
        prompt -- a full directory walk and frontmatter parse of *every* installed skill and
        agent, not just the handful the keyword table actually named. Only the matched
        candidates' own existence should ever be checked."""
        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        make_skill(skills, "reviewer")
        agents.mkdir()
        # A decoy that would make a full enumeration slow/observable if it ever ran.
        make_skill(skills, "some-other-skill-entirely")

        calls: list[str] = []
        original = install._routing_names

        def spy(*args: object, **kwargs: object):
            calls.append("called")
            return original(*args, **kwargs)  # type: ignore[arg-type]

        monkeypatch.setattr(install, "_routing_names", spy)
        text = install.route_text("please review this pull request", skills, agents)
        assert "reviewer" in text
        assert calls == [], (
            "route_text must check only the matched candidate names' own existence, not "
            "enumerate every installed skill via _routing_names"
        )

    def test_stays_fast_with_many_installed_skills(self, tmp_path: Path) -> None:
        """The behavioural twin of the spy test above: with hundreds of installed skills on
        disk, routing a single prompt must stay fast -- it no longer has any reason to scale
        with how much is installed."""
        import time

        skills = tmp_path / "skills"
        agents = tmp_path / "agents"
        for i in range(400):
            make_skill(skills, f"decoy-skill-{i:04d}")
        make_skill(skills, "reviewer")
        agents.mkdir()

        start = time.monotonic()
        text = install.route_text("please review this pull request", skills, agents)
        elapsed = time.monotonic() - start

        assert "reviewer" in text
        assert elapsed < 1.0, (
            f"route_text took {elapsed:.3f}s with 400 installed skills"
        )


class TestRouteOutputShape:
    def test_output_stays_under_the_character_cap(self, core_skills) -> None:
        skills, agents = core_skills
        for _category, _lang, prompt, _expected in SDLC_CASES:
            text = install.route_text(prompt, skills, agents)
            assert len(text) < 600, f"{prompt!r} -> {len(text)} chars"

    def test_route_json_is_the_user_prompt_submit_shape(self, core_skills) -> None:
        skills, agents = core_skills
        out = install.route_json("please review this pull request", skills, agents)
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"
        assert "reviewer" in payload["hookSpecificOutput"]["additionalContext"]

    def test_route_json_is_empty_string_on_no_match(self, core_skills) -> None:
        skills, agents = core_skills
        out = install.route_json("let's chat about the weather today", skills, agents)
        assert out == ""

    def test_route_json_never_raises_on_a_broken_table(
        self, core_skills, monkeypatch
    ) -> None:
        skills, agents = core_skills

        def boom(*_a, **_k):
            raise ValueError("boom")

        monkeypatch.setattr(install, "_load_route_table", boom)
        assert (
            install.route_json("please review this pull request", skills, agents) == ""
        )


class TestRouteCli:
    def test_cli_route_prints_json_on_a_matching_prompt(
        self, core_skills, capsys, monkeypatch
    ) -> None:
        skills, agents = core_skills
        monkeypatch.setattr(
            sys,
            "stdin",
            __import__("io").StringIO(
                json.dumps({"prompt": "please review this pull request"})
            ),
        )
        code = install.main(
            ["route", "--target", str(skills), "--agents-target", str(agents)]
        )
        assert code == 0
        out = capsys.readouterr().out.strip()
        payload = json.loads(out)
        assert payload["hookSpecificOutput"]["hookEventName"] == "UserPromptSubmit"

    def test_cli_route_prints_nothing_on_no_match(
        self, core_skills, capsys, monkeypatch
    ) -> None:
        skills, agents = core_skills
        monkeypatch.setattr(
            sys,
            "stdin",
            __import__("io").StringIO(json.dumps({"prompt": "the weather today"})),
        )
        code = install.main(
            ["route", "--target", str(skills), "--agents-target", str(agents)]
        )
        assert code == 0
        assert capsys.readouterr().out == ""

    def test_cli_route_never_crashes_on_malformed_stdin(
        self, core_skills, capsys, monkeypatch
    ) -> None:
        skills, agents = core_skills
        monkeypatch.setattr(sys, "stdin", __import__("io").StringIO("not json at all"))
        code = install.main(
            ["route", "--target", str(skills), "--agents-target", str(agents)]
        )
        assert code == 0
        assert capsys.readouterr().out == ""


class TestPromptFromStdinIsBounded:
    """DG-515 review round 2: ``_prompt_from_stdin`` used to call ``sys.stdin.read()`` with no
    limit at all -- a hook fed an unbounded stream reads the whole thing into memory before
    ``json.loads`` ever runs. It must read at most a fixed cap, and a short, valid prompt that
    arrives within that cap must still route correctly even with megabytes of data behind it."""

    def test_a_50mb_stdin_finishes_quickly_and_still_routes_the_short_prefix(
        self, core_skills, monkeypatch
    ) -> None:
        import io
        import time

        skills, agents = core_skills
        payload = json.dumps({"prompt": "please review this pull request"})
        # The valid JSON prompt first, then ~50MB of padding behind it on the same stream --
        # exactly what an unbounded `.read()` would otherwise load in full.
        huge = payload + ("x" * (50 * 1024 * 1024))
        monkeypatch.setattr(sys, "stdin", io.StringIO(huge))

        start = time.monotonic()
        prompt = install._prompt_from_stdin()
        elapsed = time.monotonic() - start

        assert elapsed < 1.0, f"_prompt_from_stdin took {elapsed:.3f}s on a 50MB stream"
        assert prompt == "please review this pull request"

    def test_reads_at_most_the_stdin_cap(self, monkeypatch) -> None:
        import io

        seen: list[int] = []
        real_stringio = io.StringIO("x" * (2 * install._ROUTE_STDIN_CAP))
        original_read = real_stringio.read

        def spy_read(size=-1):  # noqa: ANN001 - mirrors io.StringIO.read's own signature
            seen.append(size if size is not None else -1)
            return original_read(size)

        real_stringio.read = spy_read  # type: ignore[method-assign]
        monkeypatch.setattr(sys, "stdin", real_stringio)
        install._prompt_from_stdin()
        assert seen, "stdin.read was never called"
        assert all(0 < n <= install._ROUTE_STDIN_CAP for n in seen), seen


class TestRouteHook:
    def test_plan_reports_add_when_settings_file_is_absent(
        self, tmp_path: Path, stub_resolve_route
    ) -> None:
        settings_path = tmp_path / "settings.json"
        plan = install.plan_route_hook(settings_path, remove=False)
        assert plan.action == "add"

    def test_apply_writes_a_user_prompt_submit_entry(
        self, tmp_path: Path, stub_resolve_route
    ) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_route_hook(settings_path, apply=True)
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        commands = [
            h.get("command")
            for entry in data["hooks"]["UserPromptSubmit"]
            for h in entry.get("hooks", [])
        ]
        assert BARE_ROUTE in commands

    def test_is_idempotent(self, tmp_path: Path, stub_resolve_route) -> None:
        settings_path = tmp_path / "settings.json"
        install.apply_route_hook(settings_path, apply=True)
        first = settings_path.read_text(encoding="utf-8")
        install.apply_route_hook(settings_path, apply=True)
        second = settings_path.read_text(encoding="utf-8")
        assert first == second

    def test_backs_up_the_original_before_the_first_change(
        self, tmp_path: Path, stub_resolve_route
    ) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(json.dumps({"permissions": {}}), encoding="utf-8")
        original = settings_path.read_text(encoding="utf-8")
        install.apply_route_hook(settings_path, apply=True)
        backups = list(tmp_path.glob("settings.json.bak-*"))
        assert len(backups) == 1
        assert backups[0].read_text(encoding="utf-8") == original

    def test_remove_undoes_exactly_the_guild_route_entry(
        self, tmp_path: Path, stub_resolve_route
    ) -> None:
        settings_path = tmp_path / "settings.json"
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
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
        install.apply_route_hook(settings_path, apply=True)
        install.apply_route_hook(settings_path, apply=True, remove=True)
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        commands = [
            h.get("command")
            for entry in data["hooks"]["UserPromptSubmit"]
            for h in entry.get("hooks", [])
        ]
        assert BARE_ROUTE not in commands
        assert "echo other" in commands

    def test_a_look_alike_route_command_is_rejected(self) -> None:
        assert (
            install._is_guild_route_command('"not-drunken-install.exe" route') is False
        )

    def test_an_extra_argument_is_rejected(self) -> None:
        assert install._is_guild_route_command("drunken-install route extra") is False

    def test_accepts_the_bare_route_command(self) -> None:
        assert install._is_guild_route_command(install.GUILD_ROUTE_FALLBACK) is True

    def test_cli_hook_apply_merges_both_session_and_route_entries(
        self, tmp_path: Path, stub_resolve_route, monkeypatch, capsys
    ) -> None:
        monkeypatch.setattr(
            install, "resolve_hook_command", lambda: (install.GUILD_HOOK_FALLBACK, True)
        )
        settings_path = tmp_path / "settings.json"
        code = install.main(["hook", "--settings", str(settings_path), "--apply"])
        assert code == 0
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "SessionStart" in data["hooks"]
        assert "UserPromptSubmit" in data["hooks"]

    def test_cli_hook_apply_then_apply_again_is_idempotent_for_both_entries(
        self, tmp_path: Path, stub_resolve_route, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            install, "resolve_hook_command", lambda: (install.GUILD_HOOK_FALLBACK, True)
        )
        settings_path = tmp_path / "settings.json"
        install.main(["hook", "--settings", str(settings_path), "--apply"])
        first = settings_path.read_text(encoding="utf-8")
        install.main(["hook", "--settings", str(settings_path), "--apply"])
        second = settings_path.read_text(encoding="utf-8")
        assert first == second

    def test_cli_hook_remove_removes_both_entries(
        self, tmp_path: Path, stub_resolve_route, monkeypatch
    ) -> None:
        monkeypatch.setattr(
            install, "resolve_hook_command", lambda: (install.GUILD_HOOK_FALLBACK, True)
        )
        settings_path = tmp_path / "settings.json"
        install.main(["hook", "--settings", str(settings_path), "--apply"])
        install.main(["hook", "--settings", str(settings_path), "--apply", "--remove"])
        data = json.loads(settings_path.read_text(encoding="utf-8"))
        assert "hooks" not in data or not data["hooks"]


class TestIsTrustedRouteHookCommand:
    def test_trusts_the_path_resolve_route_hook_command_would_itself_produce(
        self, tmp_path, monkeypatch
    ) -> None:
        real = tmp_path / "drunken-install.exe"
        real.write_bytes(b"")
        monkeypatch.setattr(
            install, "resolve_route_hook_command", lambda: (f'"{real}" route', True)
        )
        assert install.is_trusted_route_hook_command(f'"{real}" route') is True

    def test_does_not_trust_a_same_named_file_in_a_different_directory(
        self, tmp_path, monkeypatch
    ) -> None:
        real = tmp_path / "real" / "drunken-install.exe"
        real.parent.mkdir()
        real.write_bytes(b"")
        attacker = tmp_path / "attacker" / "drunken-install.exe"
        attacker.parent.mkdir()
        attacker.write_bytes(b"")
        monkeypatch.setattr(
            install, "resolve_route_hook_command", lambda: (f'"{real}" route', True)
        )
        monkeypatch.setattr(install.shutil, "which", lambda name: None)
        assert install.is_trusted_route_hook_command(f'"{attacker}" route') is False


class TestVerifyRouteHookCommand:
    def test_ok_when_the_command_prints_the_expected_json_for_a_matching_prompt(
        self,
    ) -> None:
        skills = Path(__file__).resolve().parent.parent / "skills"
        agents = Path(__file__).resolve().parent.parent / "agents"
        script = (
            "import json,sys; sys.path.insert(0, 'src'); from core import install as i; "
            f"print(i.route_json(json.load(sys.stdin).get('prompt',''), r'{skills}', r'{agents}'))"
        )
        command = f'"{sys.executable}" -c "{script}"'
        ok, reason = install.verify_route_hook_command(command)
        assert ok is True, reason

    def test_empty_command_is_reported_rather_than_run(self) -> None:
        ok, reason = install.verify_route_hook_command("")
        assert ok is False
        assert "no command" in reason

    def test_not_found_when_the_program_does_not_exist(self, tmp_path) -> None:
        missing = tmp_path / "does-not-exist-drunken-install.exe"
        ok, reason = install.verify_route_hook_command(f'"{missing}" route')
        assert ok is False
        assert "not found" in reason


class TestDoctorPromptHookCheck:
    def test_warns_when_not_present(self, tmp_path: Path) -> None:
        from core import doctor

        settings_path = tmp_path / "settings.json"
        report = doctor.Report()
        doctor._check_prompt_hook(report, settings_path)
        check = next(c for c in report.checks if c.name == "routes.prompt_hook")
        assert check.status == "warn"

    def test_warns_on_untrusted_but_matching_command_without_executing_it(
        self, tmp_path: Path, monkeypatch
    ) -> None:
        from core import doctor

        settings_path = tmp_path / "settings.json"
        attacker = tmp_path / "drunken-install.exe"
        attacker.write_bytes(b"")
        settings_path.write_text(
            json.dumps(
                {
                    "hooks": {
                        "UserPromptSubmit": [
                            {
                                "matcher": "",
                                "hooks": [
                                    {
                                        "type": "command",
                                        "command": f'"{attacker}" route',
                                    }
                                ],
                            }
                        ]
                    }
                }
            ),
            encoding="utf-8",
        )
        monkeypatch.setattr(
            install, "resolve_route_hook_command", lambda: (BARE_ROUTE, False)
        )
        monkeypatch.setattr(install.shutil, "which", lambda name: None)

        def must_not_run(*_args, **_kwargs):
            raise AssertionError(
                "subprocess.run must not be called for an untrusted command"
            )

        monkeypatch.setattr(install.subprocess, "run", must_not_run)
        report = doctor.Report()
        doctor._check_prompt_hook(report, settings_path)
        check = next(c for c in report.checks if c.name == "routes.prompt_hook")
        assert check.status == "warn"
        assert "not this installation" in check.detail
