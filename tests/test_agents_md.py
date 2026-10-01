# mypy: ignore-errors
"""DG-390. AGENTS.md is the one instruction file every agent reads; CLAUDE.md
must not hold a rule AGENTS.md lacks, and nothing may still point at
SESSION_CHECKPOINT.md §0 as the source of the 2.0.0 target — that moved to
.ai/PRD.md.
"""

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Every-agent rules lifted out of CLAUDE.md. Each is a substring that has to
# survive the move into AGENTS.md — not a restatement, the same rule.
EVERY_AGENT_RULES = (
    "Never push to `main`",
    "An agent opens pull requests; a human merges them",
    "Never `git merge` locally against `main` or `develop`",
    "Merge strategy is chosen by target, not preference",
    "`Claude Code <claude@drunken.local>`",
    "Two agents never share a checked-out working tree",
    "Never skip IN REVIEW",
    "agent:<name>` in `labels`",
    "No secret ever enters a commit",
    "An agent does not delete",
    "An agent does not install and does not deploy",
    "no decision, so the harness prompts exactly as it would have",
)


def test_agents_md_exists() -> None:
    assert (REPO_ROOT / "AGENTS.md").is_file()


def test_agents_md_opens_with_a_guild_block() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert "<!-- guild-block:start -->" in text
    assert "<!-- guild-block:end -->" in text
    start = text.index("<!-- guild-block:start -->")
    # The block is the opening of the file, not buried after other content.
    assert text[:start].count("\n") < 10


def test_guild_block_routes_every_named_situation() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    block = text.split("<!-- guild-block:start -->", 1)[1].split(
        "<!-- guild-block:end -->", 1
    )[0]
    for situation in (
        "new project",
        "/prd",
        "/clarify",
        "/ddd",
        "/breakdown",
        "/replan",
        "ticket",
        "/build",
        "worker",
        "reviewer",
        "planning",
        "manager",
        "git",
        "git-workflow",
        "Jira",
        "jira-tickets",
        "jira_",
        "end of day",
        "/audit",
        "unsure",
        "INDEX",
    ):
        assert situation in block, f"guild block names no route for {situation!r}"


def test_claude_md_holds_no_rule_agents_md_lacks() -> None:
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    agents = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    for rule in EVERY_AGENT_RULES:
        assert rule in claude, f"fixture drifted: {rule!r} is no longer in CLAUDE.md"
        assert rule in agents, f"CLAUDE.md names a rule AGENTS.md lacks: {rule!r}"


def test_nothing_cites_session_checkpoint_section_0_as_the_2_0_0_source() -> None:
    skipped = {".venv", ".git", "node_modules", "build", ".claude", ".mypy_cache"}
    for path in REPO_ROOT.rglob("*.md"):
        if skipped & set(path.relative_to(REPO_ROOT).parts):
            continue
        if path.name == "SESSION_CHECKPOINT.md":
            # Its own job is to record what moved and why -- it is allowed to
            # say the pointer used to be here.
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        assert "SESSION_CHECKPOINT.md` §0" not in text, (
            f"{path.relative_to(REPO_ROOT)} still names SESSION_CHECKPOINT.md "
            "§0 as the 2.0.0 target; that moved to .ai/PRD.md"
        )


def test_retired_md_records_agents_md_reintroduced() -> None:
    retired = (REPO_ROOT / "RETIRED.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in retired
    assert "DG-390" in retired
