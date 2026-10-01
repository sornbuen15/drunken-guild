# mypy: ignore-errors
"""DG-390. AGENTS.md is the one instruction file every agent reads; CLAUDE.md
must not hold a rule AGENTS.md lacks, and nothing may still point at
SESSION_CHECKPOINT.md §0 as the source of the 2.0.0 target — that moved to
.ai/PRD.md.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# A hand-picked substring list drifts silently the next time a paragraph is
# edited in one file and not the other. This instead walks every rule-shaped
# unit of CLAUDE.md -- a paragraph, or one bullet/numbered item of a list --
# and checks it survived into AGENTS.md. Headings, the horizontal rules,
# fenced code and table rows are not rules and are skipped.
_LIST_ITEM = re.compile(r"\n(?=-\s|\d+\.\s)")


def _normalize(text: str) -> str:
    """Line-wrap width differs between the two files; only the words matter."""
    return re.sub(r"\s+", " ", text).strip()


def _rule_units(text: str) -> list[str]:
    units = []
    for block in text.split("\n\n"):
        stripped = block.strip()
        if not stripped:
            continue
        if stripped.startswith("#") or stripped == "---" or "```" in stripped:
            continue
        if stripped.startswith("|"):  # a table row, not a rule
            continue
        if stripped.startswith("- ") or stripped.startswith("1. "):
            units.extend(
                item.strip() for item in _LIST_ITEM.split(stripped) if item.strip()
            )
        else:
            units.append(stripped)
    return units


# Rule units that are *intentionally* reworded rather than carried verbatim,
# each because the CLAUDE.md wording is not vendor-neutral. The move itself
# is the point of DG-390, so these three are not a gap:
#   - the opening paragraph describes `.claude/rules/` `paths:` loading,
#     which is a Claude Code mechanism CLAUDE.md itself uses to load this
#     file's other half -- AGENTS.md states the same "every agent, same
#     rules" fact without describing Claude's own loading mechanics;
#   - "Another agent working here follows this same file" is self-referential
#     to CLAUDE.md; AGENTS.md *is* that file now, so it states the rule
#     (same rules, agent's name in the author and the `agent:` label)
#     without the self-reference;
#   - "a copy into `~/.claude/`" names Claude's own install path; AGENTS.md
#     says "a copy into an agent's own config directory" to hold for every
#     agent, not only Claude.
_VENDOR_NEUTRAL_REWORDING = (
    "Loaded on every turn, so it holds only what must be true",
    "Another agent working here follows this same file",
    "not a copy into `~/.claude/`",
)


def _is_known_rewording(unit: str) -> bool:
    return any(marker in unit for marker in _VENDOR_NEUTRAL_REWORDING)


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
    agents_norm = _normalize(agents)

    units = _rule_units(claude)
    assert len(units) > 30, "the parser found too few rule units to prove anything"

    missing = [
        unit
        for unit in units
        if not _is_known_rewording(unit) and _normalize(unit) not in agents_norm
    ]
    assert not missing, "CLAUDE.md names a rule AGENTS.md lacks:\n  " + "\n  ".join(
        u[:160] for u in missing
    )


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
