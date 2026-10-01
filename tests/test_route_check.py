# mypy: ignore-errors
"""DG-401. drunken-doctor fails when a routed skill, role or tool does not
exist, or a skill is reachable from nowhere.

REQ-013: a check that every route resolves. The routes are the guild block's
pointer table in AGENTS.md (REQ-011) and each skill's own description, which is
how an agent finds it with no route at all (REQ-010/REQ-012).
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


def _agent(root: Path, name: str) -> Path:
    agents_dir = root / "agents"
    agents_dir.mkdir(exist_ok=True)
    path = agents_dir / f"{name}.md"
    path.write_text(f"---\nname: {name}\ndescription: role\n---\n", encoding="utf-8")
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


class TestRegisteredMcpTools:
    def test_reads_the_name_following_mcp_tool(self, tmp_path):
        server = _server(tmp_path, ["jira_search_issues", "jira_add_comment"])

        names = doctor.registered_mcp_tools(server)

        assert names == ["jira_search_issues", "jira_add_comment"]

    def test_an_absent_server_file_reads_as_no_tools(self, tmp_path):
        assert doctor.registered_mcp_tools(tmp_path / "nope.py") == []


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
    def test_a_skill_with_no_description_and_no_route_is_unreachable(self, tmp_path):
        _skill(tmp_path, "flow", "orphan")
        agents_md_text = doctor.guild_block(
            _agents_md(tmp_path, ["| **x** | `/prd` |"]).read_text(encoding="utf-8")
        )

        unreachable = doctor.unreachable_skills(tmp_path / "skills", agents_md_text)

        assert unreachable == ["orphan"]

    def test_a_skill_with_a_description_is_reachable_on_its_own(self, tmp_path):
        _skill(tmp_path, "flow", "prd", "Use for a new project.")

        unreachable = doctor.unreachable_skills(tmp_path / "skills", "")

        assert unreachable == []

    def test_a_skill_with_no_description_but_a_route_is_reachable(self, tmp_path):
        _skill(tmp_path, "flow", "orphan")

        unreachable = doctor.unreachable_skills(tmp_path / "skills", "`/orphan`")

        assert unreachable == []

    def test_a_skill_with_no_description_named_by_another_skills_next_step_is_reachable(
        self, tmp_path
    ):
        _skill(tmp_path, "flow", "orphan")
        _skill(tmp_path, "flow", "upstream", "Use upstream. Next step: /orphan.")

        unreachable = doctor.unreachable_skills(tmp_path / "skills", "")

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

    def test_a_skill_reachable_from_nowhere_is_reported(self, tmp_path):
        self._fixture(
            tmp_path,
            rows=["| **x** | `/prd` |"],
            skills=[
                ("flow", "prd", "Use for a new project."),
                ("flow", "orphan", ""),
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


class TestTheRealRepoPasses:
    """The actual repository's AGENTS.md and skills/, run through the check
    with no fixture at all -- the check must not fail on real content."""

    def test_the_real_repo_resolves_every_route_and_reaches_every_skill(self):
        repo_root = Path(__file__).resolve().parent.parent

        report = doctor.Report()
        doctor._check_routes(report, repo_root=repo_root)

        for name in ("routes.targets", "routes.reachable"):
            entry = next(c for c in report.checks if c.name == name)
            assert entry.status == "ok", entry.detail
