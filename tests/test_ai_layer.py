# mypy: ignore-errors
"""DG-437 (REQ-019). One list of what makes up a project's AI layer, so
init, doctor and the exclude writer cannot each grow their own and drift.
"""

from pathlib import Path

from core import ai_layer, scaffold


class TestEveryListedPathIsRecognised:
    def test_agents_md(self) -> None:
        assert ai_layer.is_ai_layer_path("AGENTS.md")

    def test_claude_md(self) -> None:
        assert ai_layer.is_ai_layer_path("CLAUDE.md")

    def test_gemini_md(self) -> None:
        assert ai_layer.is_ai_layer_path("GEMINI.md")

    def test_aider_conf(self) -> None:
        assert ai_layer.is_ai_layer_path(".aider.conf.yml")

    def test_conventions_md(self) -> None:
        # Aider's own instruction file — templates/.aider.conf.yml loads it
        # alongside CLAUDE.md; templates/CONVENTIONS.md describes itself as
        # living in the project root, beside .aider.conf.yml.
        assert ai_layer.is_ai_layer_path("CONVENTIONS.md")

    def test_claude_local_md(self) -> None:
        # Claude Code's personal override file. Not verified against live
        # docs — included on the reviewer's instruction, said here plainly.
        assert ai_layer.is_ai_layer_path("CLAUDE.local.md")

    def test_claude_dir_itself(self) -> None:
        assert ai_layer.is_ai_layer_path(".claude")
        assert ai_layer.is_ai_layer_path(".claude/")

    def test_claude_dir_nested_file(self) -> None:
        assert ai_layer.is_ai_layer_path(".claude/settings.json")
        assert ai_layer.is_ai_layer_path(".claude/settings.local.json")
        assert ai_layer.is_ai_layer_path(".claude/rules/python.md")

    def test_gemini_dir_itself(self) -> None:
        assert ai_layer.is_ai_layer_path(".gemini")

    def test_gemini_dir_nested_file(self) -> None:
        assert ai_layer.is_ai_layer_path(".gemini/settings.json")

    def test_backslash_paths_are_normalised(self) -> None:
        # A Windows-style separator must not change the answer — CI runs on
        # Linux, so this cannot be exercised by relying on OS path semantics;
        # it is asserted directly on the string instead.
        assert ai_layer.is_ai_layer_path(".claude\\settings.json")

    def test_leading_dot_slash_is_normalised(self) -> None:
        assert ai_layer.is_ai_layer_path("./AGENTS.md")


class TestInstructionBasenamesMatchAtAnyDepth:
    """A monorepo's instruction files are not only at the repository root —
    Claude Code, Gemini CLI and Antigravity all read one next to the code it
    describes. Matched on the file's own basename, any depth.
    """

    def test_nested_claude_md_one_level_down(self) -> None:
        assert ai_layer.is_ai_layer_path("packages/x/CLAUDE.md")

    def test_nested_agents_md_two_levels_down(self) -> None:
        assert ai_layer.is_ai_layer_path("sub/dir/AGENTS.md")

    def test_nested_gemini_md(self) -> None:
        assert ai_layer.is_ai_layer_path("packages/y/GEMINI.md")

    def test_backslash_nested_path_is_normalised(self) -> None:
        assert ai_layer.is_ai_layer_path("packages\\x\\CLAUDE.md")


class TestWorkIsNotTheAiLayer:
    def test_prd(self) -> None:
        assert not ai_layer.is_ai_layer_path(".ai/PRD.md")

    def test_domain(self) -> None:
        assert not ai_layer.is_ai_layer_path(".ai/DOMAIN.md")

    def test_readme(self) -> None:
        assert not ai_layer.is_ai_layer_path("README.md")

    def test_a_source_file(self) -> None:
        assert not ai_layer.is_ai_layer_path("src/core/scaffold.py")

    def test_empty_path(self) -> None:
        assert not ai_layer.is_ai_layer_path("")


class TestMcpJsonIsAiLayer:
    """DG-457 / REQ-019 Decided 2026-10-10."""

    def test_mcp_config_is_ai_layer(self) -> None:
        # DG-457, REQ-019 Decided 2026-10-10: a project has no .mcp.json at
        # all -- the server is declared once per machine at user scope -- so a
        # tracked one is AI-layer content that `layering.tracked` must flag.
        assert ai_layer.is_ai_layer_path(".mcp.json")

    def test_mcp_config_is_root_only(self) -> None:
        # Root-only, like .aider.conf.yml: a nested fixture or example
        # .mcp.json (docs/examples/.mcp.json) is a file about MCP, not the
        # project's own declaration.
        assert not ai_layer.is_ai_layer_path("docs/examples/.mcp.json")
        assert not ai_layer.is_ai_layer_path("sub/.mcp.json")

    def test_similar_names_do_not_match(self) -> None:
        assert not ai_layer.is_ai_layer_path(".mcp.json.bak")
        assert not ai_layer.is_ai_layer_path("mcp.json")


class TestNoFalsePositives:
    """A near-miss by name or by prefix must not match — a false positive
    here is `drunken-doctor` refusing to look at a file that is actually the
    project's own work.
    """

    def test_claude_notes_directory_is_not_dot_claude(self) -> None:
        assert not ai_layer.is_ai_layer_path(".claude-notes/x")

    def test_dot_claude_prefix_without_separator(self) -> None:
        assert not ai_layer.is_ai_layer_path(".claudeX")

    def test_lowercase_agents_md_is_a_different_file(self) -> None:
        # Deliberate: this checks a path against a tracked git index, which
        # is case-sensitive. "agents.md" and "AGENTS.md" are different blobs
        # there, so not matching the lowercase variant is correct, not an
        # oversight — nothing claims a project actually has one today.
        assert not ai_layer.is_ai_layer_path("agents.md")

    def test_backup_suffix_is_not_the_instruction_file(self) -> None:
        assert not ai_layer.is_ai_layer_path("docs/CLAUDE.md.bak")

    def test_prefixed_name_is_not_the_instruction_file(self) -> None:
        assert not ai_layer.is_ai_layer_path("my-AGENTS.md")


class TestScaffoldOutputStaysInsideTheList:
    """The mutation ACCEPTANCE asks for: every file the scaffold writes for
    an agent must be recognised by `is_ai_layer_path`, or the two have
    drifted exactly the way this module exists to prevent.
    """

    def test_every_file_instruction_files_writes_is_in_the_list(
        self, tmp_path: Path
    ) -> None:
        checkout = tmp_path / "project"
        checkout.mkdir()

        scaffold.instruction_files(checkout, "sample", None)

        written = sorted(
            p.relative_to(checkout).as_posix()
            for p in checkout.rglob("*")
            if p.is_file()
        )
        assert written, "scaffold.instruction_files() wrote nothing to check"

        not_recognised = [
            relative for relative in written if not ai_layer.is_ai_layer_path(relative)
        ]
        assert not_recognised == [], (
            "scaffold.instruction_files() wrote a file not recognised by "
            f"ai_layer.is_ai_layer_path: {not_recognised}. Add it to "
            "AI_LAYER_BASENAMES, AI_LAYER_ROOT_FILES or AI_LAYER_ROOT_DIRS."
        )


class TestContentScanPathIsBroaderThanTheCopyInList:
    """DG-508: `is_content_scan_path` is a *second*, wider predicate used only to decide what
    `drunken-doctor`'s content_scan reads for leaked-secret-shaped content — never to decide what
    the config-repo copy-in provides, and never `is_ai_layer_path` itself (`layering.tracked` and
    the copy-in keep reading exactly what they always did).
    """

    def test_everything_is_ai_layer_path_recognises_is_still_recognised(self) -> None:
        # The narrower predicate is a strict subset — nothing it already covers may regress.
        for path in (
            "AGENTS.md",
            "CLAUDE.md",
            ".claude",
            ".claude/settings.json",
            ".mcp.json",
        ):
            assert ai_layer.is_content_scan_path(path), path

    def test_nested_claude_settings_json_is_scanned(self) -> None:
        # Claude Code's own settings docs (code.claude.com/docs/en/settings, "Where Claude Code
        # keeps the local file in a git repository" / main body): "Claude Code reads the shared
        # `.claude/settings.json` from the session's primary working directory" — a session
        # started inside `packages/x/` reads `packages/x/.claude/settings.json`, not only a
        # root one. `is_ai_layer_path` stays root-only (no change); this wider predicate must
        # not.
        assert ai_layer.is_content_scan_path("packages/x/.claude/settings.json")
        assert not ai_layer.is_ai_layer_path("packages/x/.claude/settings.json")

    def test_nested_gemini_settings_json_is_scanned(self) -> None:
        assert ai_layer.is_content_scan_path("packages/x/.gemini/settings.json")

    def test_differently_cased_root_claude_dir_is_scanned(self) -> None:
        # NTFS and APFS (default) are case-insensitive, the same filesystem fact DG-453 already
        # relies on for the tracked-file check: `.Claude/` and `.claude/` are the very same
        # on-disk directory there, so a case-sensitive `is_ai_layer_path` comparison alone
        # misses it.
        assert ai_layer.is_content_scan_path(".Claude/settings.json")
        assert not ai_layer.is_ai_layer_path(".Claude/settings.json")

    def test_nested_mcp_json_is_scanned_though_unverified(self) -> None:
        # No citation found: Claude Code's own MCP docs (code.claude.com/docs/en/mcp) say only
        # "a `.mcp.json` file at your project's root directory" / "at your project root", and
        # never discuss a nested copy. Scanned anyway, on the "where unsure, scan it" side of
        # DG-508's SCOPE — a credential sitting there is still a credential.
        assert ai_layer.is_content_scan_path("packages/x/.mcp.json")
        assert not ai_layer.is_ai_layer_path("packages/x/.mcp.json")

    def test_a_claude_notes_directory_is_still_not_matched(self) -> None:
        # The basename-substring guard already on is_ai_layer_path must not be loosened here:
        # a `.claude-notes/` segment is not `.claude/`, whatever its case.
        assert not ai_layer.is_content_scan_path(".claude-notes/x")
        assert not ai_layer.is_content_scan_path(".ClaudeNotes/x")

    def test_an_unrelated_file_is_still_not_matched(self) -> None:
        assert not ai_layer.is_content_scan_path("src/core/scaffold.py")
        assert not ai_layer.is_content_scan_path("README.md")
