# mypy: ignore-errors
"""DG-401. drunken-doctor fails when a routed skill, role or tool does not
exist, or a skill is reachable from nowhere.

REQ-013: a check that every route resolves. The routes are the guild block's
pointer table in AGENTS.md (REQ-011) and each skill's own "next step"
hand-off (REQ-012). A skill's own description (REQ-010) is a separate fact —
it is how an agent *picks* a skill, not whether anything routes to it — so it
is deliberately not asked here: the Boss's approved wording is that a skill
is reachable only via the guild block, an agent file, or another skill's
text.
"""

from pathlib import Path

from core import doctor

AGENTS_MD_TEMPLATE = """# AGENTS.md — fixture

<!-- guild-block:start -->
| situation | pick up |
|---|---|
{rows}
<!-- guild-block:end -->

Body text below the block, not part of it.
"""


def _skill(root: Path, category: str, name: str, description: str = "") -> Path:
    skill_dir = root / "skills" / category / name
    skill_dir.mkdir(parents=True)
    frontmatter_description = (
        f"description: {description}\n" if description else "description:\n"
    )
    (skill_dir / "SKILL.md").write_text(
        f"---\nname: {name}\n{frontmatter_description}---\n\n# Skill: {name}\n",
        encoding="utf-8",
    )
    return skill_dir


def _agent(root: Path, name: str, body: str = "") -> Path:
    agents_dir = root / "agents"
    agents_dir.mkdir(exist_ok=True)
    path = agents_dir / f"{name}.md"
    path.write_text(
        f"---\nname: {name}\ndescription: role\n---\n{body}", encoding="utf-8"
    )
    return path


def _server(root: Path, tool_names: list[str]) -> Path:
    src = root / "src" / "jira_mcp"
    src.mkdir(parents=True)
    body = "\n\n".join(
        f"@mcp.tool()  # type: ignore[misc]\n"
        f"@as_tool_result\nasync def {name}(project: str) -> str:\n    return ''"
        for name in tool_names
    )
    path = src / "server.py"
    path.write_text(body, encoding="utf-8")
    return path


def _agents_md(root: Path, rows: list[str]) -> Path:
    path = root / "AGENTS.md"
    path.write_text(AGENTS_MD_TEMPLATE.format(rows="\n".join(rows)), encoding="utf-8")
    return path


class TestGuildBlock:
    def test_extracts_only_the_text_between_the_markers(self, tmp_path):
        agents_md = _agents_md(tmp_path, ["| **x** | `/prd` |"])
        text = agents_md.read_text(encoding="utf-8")

        block = doctor.guild_block(text)

        assert "/prd" in block
        assert "Body text below the block" not in block

    def test_an_absent_block_is_empty(self):
        assert doctor.guild_block("no markers here") == ""


class TestRouteTargets:
    def test_finds_code_spans_and_bold_role_names(self):
        block = "| x | `/build`, run by the **worker** role. |"

        targets = doctor.route_targets(block)

        assert "/build" in targets
        assert "worker" in targets


class TestUnresolvedRoutes:
    def test_a_route_naming_a_missing_skill_is_reported(self, tmp_path):
        _skill(tmp_path, "flow", "prd", "Use for a new project.")
        skills_root = tmp_path / "skills"
        agents_root = tmp_path / "agents"
        agents_root.mkdir()

        missing = doctor.unresolved_routes(
            ["/prd", "/nonexistent-skill"], skills_root, agents_root, []
        )

        assert missing == ["/nonexistent-skill"]

    def test_an_existing_skill_slash_command_resolves(self, tmp_path):
        _skill(tmp_path, "flow", "prd", "Use for a new project.")
        skills_root = tmp_path / "skills"
        agents_root = tmp_path / "agents"
        agents_root.mkdir()

        missing = doctor.unresolved_routes(["/prd"], skills_root, agents_root, [])

        assert missing == []

    def test_a_role_with_no_agent_file_is_reported(self, tmp_path):
        skills_root = tmp_path / "skills"
        skills_root.mkdir()
        agents_root = tmp_path / "agents"
        agents_root.mkdir()
        # worker.md exists, reviewer.md does not.
        (agents_root / "worker.md").write_text("x", encoding="utf-8")

        missing = doctor.unresolved_routes(
            ["worker", "reviewer"], skills_root, agents_root, []
        )

        assert missing == ["reviewer"]

    def test_a_skill_md_path_is_checked_as_a_file(self, tmp_path):
        skills_root = tmp_path / "skills"
        agents_root = tmp_path / "agents"
        agents_root.mkdir()
        _skill(tmp_path, "workflow", "git-workflow", "Use for git.")

        missing = doctor.unresolved_routes(
            [
                "skills/workflow/git-workflow/SKILL.md",
                "skills/workflow/missing-skill/SKILL.md",
            ],
            skills_root,
            agents_root,
            [],
        )

        assert missing == ["skills/workflow/missing-skill/SKILL.md"]

    def test_a_jira_wildcard_resolves_against_any_matching_tool(self, tmp_path):
        skills_root = tmp_path / "skills"
        agents_root = tmp_path / "agents"
        agents_root.mkdir()

        missing = doctor.unresolved_routes(
            ["jira_*"], skills_root, agents_root, ["jira_search_issues"]
        )

        assert missing == []

    def test_a_wildcard_matching_nothing_is_reported(self, tmp_path):
        skills_root = tmp_path / "skills"
        agents_root = tmp_path / "agents"
        agents_root.mkdir()

        missing = doctor.unresolved_routes(
            ["jira_*"], skills_root, agents_root, ["discord_notify"]
        )

        assert missing == ["jira_*"]

    def test_a_dotdot_escaping_the_repo_root_is_reported_even_if_the_file_exists(
        self, tmp_path
    ):
        """A `.md` route target is resolved, not just read as a string — a
        path that climbs out of the repository with `..` and happens to hit
        a real file elsewhere on disk is reported exactly like a missing
        one, never followed there."""
        skills_root = tmp_path / "repo" / "skills"
        skills_root.mkdir(parents=True)
        agents_root = tmp_path / "repo" / "agents"
        agents_root.mkdir()
        outside = tmp_path / "outside.md"
        outside.write_text("not part of this repository", encoding="utf-8")

        missing = doctor.unresolved_routes(
            ["../outside.md"], skills_root, agents_root, []
        )

        assert missing == ["../outside.md"]


class TestRegisteredMcpTools:
    def test_reads_the_name_following_mcp_tool(self, tmp_path):
        server = _server(tmp_path, ["jira_search_issues", "jira_add_comment"])

        names = doctor.registered_mcp_tools(server)

        assert names == ["jira_search_issues", "jira_add_comment"]

    def test_an_absent_server_file_reads_as_no_tools(self, tmp_path):
        assert doctor.registered_mcp_tools(tmp_path / "nope.py") == []

    def test_pinned_against_the_real_server_module(self):
        """A decorator-shape change in `src/jira_mcp/server.py` — a renamed
        tool, one added or dropped, `@mcp.tool()` written differently — must
        fail this test loudly rather than silently stop being read by
        :func:`registered_mcp_tools`."""
        repo_root = Path(__file__).resolve().parent.parent
        server_path = repo_root / "src" / "jira_mcp" / "server.py"

        names = doctor.registered_mcp_tools(server_path)

        assert names == [
            "jira_search_issues",
            "jira_assign",
            "jira_create_issue",
            "jira_board_info",
            "jira_move_to_backlog",
            "jira_move_to_board",
            "jira_transition_issue",
            "jira_add_comment",
            "jira_edit_labels",
            "jira_edit_issue",
            "jira_start_task",
            "jira_submit_for_review",
        ]
        assert len(names) == 12


class TestSkillDescription:
    def test_a_plain_description_is_read(self, tmp_path):
        skill = _skill(tmp_path, "flow", "prd", "Use for a new project.")

        assert doctor.skill_description(skill / "SKILL.md") == "Use for a new project."

    def test_an_empty_description_reads_as_empty(self, tmp_path):
        skill = _skill(tmp_path, "flow", "orphan")

        assert doctor.skill_description(skill / "SKILL.md") == ""

    def test_a_block_scalar_description_is_read(self, tmp_path):
        skill_dir = tmp_path / "skills" / "flow" / "blocky"
        skill_dir.mkdir(parents=True)
        (skill_dir / "SKILL.md").write_text(
            "---\nname: blocky\ndescription: >\n  Use when the thing happens.\n"
            "  Second line too.\n---\n",
            encoding="utf-8",
        )

        description = doctor.skill_description(skill_dir / "SKILL.md")

        assert "Use when the thing happens." in description
        assert "Second line too." in description


class TestUnreachableSkills:
    def test_a_skill_with_no_route_is_unreachable(self, tmp_path):
        _skill(tmp_path, "flow", "orphan")
        agents_root = tmp_path / "agents"
        agents_root.mkdir()
        block = doctor.guild_block(
            _agents_md(tmp_path, ["| **x** | `/prd` |"]).read_text(encoding="utf-8")
        )

        unreachable = doctor.unreachable_skills(tmp_path / "skills", agents_root, block)

        assert unreachable == ["orphan"]

    def test_a_real_description_does_not_save_an_unrouted_skill(self, tmp_path):
        """HIGH finding from review: a skill with a well-formed, genuine
        description but no route, no agent-file mention and no mention in
        any other skill's text must still fail. Being a good match for an
        agent picking by description is not the same as being routed to."""
        _skill(
            tmp_path,
            "flow",
            "scratch-orphan",
            "Use when running a one-off scratch task that nothing else covers.",
        )
        agents_root = tmp_path / "agents"
        agents_root.mkdir()

        unreachable = doctor.unreachable_skills(tmp_path / "skills", agents_root, "")

        assert unreachable == ["scratch-orphan"]

    def test_a_skill_named_in_the_guild_block_is_reachable(self, tmp_path):
        _skill(tmp_path, "flow", "orphan")
        agents_root = tmp_path / "agents"
        agents_root.mkdir()

        unreachable = doctor.unreachable_skills(
            tmp_path / "skills", agents_root, "`/orphan`"
        )

        assert unreachable == []

    def test_a_skill_named_by_an_agent_file_is_reachable(self, tmp_path):
        _skill(tmp_path, "flow", "orphan")
        _agent(tmp_path, "worker", body="Delegates to `/orphan` when needed.\n")

        unreachable = doctor.unreachable_skills(
            tmp_path / "skills", tmp_path / "agents", ""
        )

        assert unreachable == []

    def test_a_skill_named_by_another_skills_next_step_is_reachable(self, tmp_path):
        _skill(tmp_path, "flow", "orphan")
        _skill(tmp_path, "flow", "upstream", "Use upstream. Next step: /orphan.")
        agents_root = tmp_path / "agents"
        agents_root.mkdir()
        # `upstream` is routed directly, so only `orphan`'s reachability via
        # the other skill's "next step" line is under test here.
        block = "`/upstream`"

        unreachable = doctor.unreachable_skills(tmp_path / "skills", agents_root, block)

        assert "orphan" not in unreachable

    def test_a_short_name_is_not_satisfied_by_a_longer_hyphenated_mention(
        self, tmp_path
    ):
        """MEDIUM finding from review: a skill named `build` must not count
        as named because another skill's prose says `rebuild` — a raw
        substring match would wrongly call that a mention."""
        _skill(tmp_path, "flow", "build")
        _skill(
            tmp_path,
            "flow",
            "upstream",
            "This step may need to rebuild the index before continuing.",
        )
        agents_root = tmp_path / "agents"
        agents_root.mkdir()
        # `upstream` is routed directly, so only whether `rebuild` satisfies
        # `build` is under test here.
        block = "`/upstream`"

        unreachable = doctor.unreachable_skills(tmp_path / "skills", agents_root, block)

        assert unreachable == ["build"]

    def test_a_short_name_matches_as_its_own_whole_word(self, tmp_path):
        """The companion positive case: an actual mention of the whole word
        does count, so the boundary fix does not become a check nothing can
        ever pass."""
        _skill(tmp_path, "flow", "build")
        _skill(
            tmp_path,
            "flow",
            "upstream",
            "This step hands off to /build once the plan is approved.",
        )
        agents_root = tmp_path / "agents"
        agents_root.mkdir()
        block = "`/upstream`"

        unreachable = doctor.unreachable_skills(tmp_path / "skills", agents_root, block)

        assert unreachable == []


class TestCheckRoutesIntegration:
    def _fixture(self, tmp_path, rows, skills, tools=(), agent_names=("worker",)):
        for category, name, description in skills:
            _skill(tmp_path, category, name, description)
        for name in agent_names:
            _agent(tmp_path, name)
        _server(tmp_path, list(tools))
        return _agents_md(tmp_path, rows)

    def test_a_route_naming_a_missing_skill_fails(self, tmp_path):
        self._fixture(
            tmp_path,
            rows=["| **x** | `/prd` → `/nonexistent-skill` |"],
            skills=[("flow", "prd", "Use for a new project.")],
        )

        report = doctor.Report()
        doctor._check_routes(report, repo_root=tmp_path)

        entry = next(c for c in report.checks if c.name == "routes.targets")
        assert entry.status == "fail"
        assert "/nonexistent-skill" in entry.detail

    def test_a_skill_reachable_from_nowhere_is_reported_even_with_a_description(
        self, tmp_path
    ):
        self._fixture(
            tmp_path,
            rows=["| **x** | `/prd` |"],
            skills=[
                ("flow", "prd", "Use for a new project."),
                (
                    "flow",
                    "orphan",
                    "Use when a well-formed description exists but no route "
                    "and no other skill ever names this one.",
                ),
            ],
        )

        report = doctor.Report()
        doctor._check_routes(report, repo_root=tmp_path)

        entry = next(c for c in report.checks if c.name == "routes.reachable")
        assert entry.status == "fail"
        assert "orphan" in entry.detail

    def test_a_clean_fixture_passes_both_checks(self, tmp_path):
        self._fixture(
            tmp_path,
            rows=[
                "| **x** | `/prd`, run by the **worker** role, plus `jira_*` tools. |"
            ],
            skills=[("flow", "prd", "Use for a new project.")],
            tools=["jira_search_issues"],
        )

        report = doctor.Report()
        doctor._check_routes(report, repo_root=tmp_path)

        for name in ("routes.targets", "routes.reachable"):
            entry = next(c for c in report.checks if c.name == name)
            assert entry.status == "ok", entry.detail

    def test_no_agents_md_is_a_skip_not_a_failure(self, tmp_path):
        (tmp_path / "skills").mkdir()

        report = doctor.Report()
        doctor._check_routes(report, repo_root=tmp_path)

        entry = next(c for c in report.checks if c.name == "routes.guild_block")
        assert entry.status == "skip"

    def test_an_installed_package_with_no_source_tree_is_a_skip(
        self, tmp_path, monkeypatch
    ):
        """LOW finding from review: `source_tree_root()` returning `None` —
        the ordinary shape of an installed package, with no `AGENTS.md` or
        `skills/` beside it — must be a skip, not a crash or a failure, when
        no `repo_root` is passed in either."""
        monkeypatch.setattr(doctor, "source_tree_root", lambda: None)

        report = doctor.Report()
        doctor._check_routes(report)

        entry = next(c for c in report.checks if c.name == "routes.guild_block")
        assert entry.status == "skip"
        assert "installed package" in entry.detail


class TestTheRealRepoPasses:
    """The actual repository's AGENTS.md, skills/ and agents/, run through
    the check with no fixture at all.

    Under the stricter, Boss-approved rule — a skill's own description no
    longer counts, only the guild block, an agent file, or another skill's
    own text — the real repository is *not* entirely clean. This test
    pins that down explicitly rather than hiding it: `routes.targets` must
    stay green (nothing names a target that doesn't exist), but
    `routes.reachable` is allowed to fail on exactly this known list, and
    on nothing else. If the list below ever needs to grow or shrink, that is
    a routing decision for the Boss, not something this test should quietly
    wave through — hence the exact equality rather than a `<=` or `in`.
    """

    def test_every_route_target_resolves(self):
        repo_root = Path(__file__).resolve().parent.parent

        report = doctor.Report()
        doctor._check_routes(report, repo_root=repo_root)

        entry = next(c for c in report.checks if c.name == "routes.targets")
        assert entry.status == "ok", entry.detail

    def test_the_known_unrouted_skills_are_exactly_this_list(self):
        """`ask-boss` is named only in AGENTS.md's prose outside the guild
        block (under "Approvals"), never inside the block itself, by no
        agent file, and by no other skill's own text — so under the literal
        rule it is unreachable. Flagged here for the Boss to decide: add a
        guild-block route for it, or accept that it is reached only by an
        agent reading AGENTS.md in full rather than the pointer table.
        """
        repo_root = Path(__file__).resolve().parent.parent

        report = doctor.Report()
        doctor._check_routes(report, repo_root=repo_root)

        entry = next(c for c in report.checks if c.name == "routes.reachable")
        assert entry.status == "fail", (
            "expected exactly the known unrouted skill(s) below; if this "
            "now passes, the list has shrunk and should be updated, not "
            "silently dropped"
        )
        assert entry.detail.startswith("1 skill(s)"), entry.detail
        assert entry.detail.rsplit(":", 1)[1].strip() == "ask-boss"
