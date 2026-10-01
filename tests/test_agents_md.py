# mypy: ignore-errors
"""DG-390/DG-391. AGENTS.md is the one instruction file every agent reads;
CLAUDE.md is now only the one-line adapter `@AGENTS.md`, and nothing may
still point at SESSION_CHECKPOINT.md §0 as the source of the 2.0.0 target --
that moved to .ai/PRD.md.
"""

import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent


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
    """DG-391, REQ-015. CLAUDE.md is now only the one-line adapter: it must
    contain `@AGENTS.md` and nothing AGENTS.md does not -- which, for a file
    that is exactly that one line, means it is exactly that one line. A rule
    added back to CLAUDE.md fails this the moment it lands, before it could
    ever drift against AGENTS.md's wording.
    """
    claude = (REPO_ROOT / "CLAUDE.md").read_text(encoding="utf-8")
    assert claude.strip() == "@AGENTS.md", (
        f"CLAUDE.md must contain the import and nothing AGENTS.md does not:\n{claude!r}"
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


def _guild_block(text: str) -> str:
    return text.split("<!-- guild-block:start -->", 1)[1].split(
        "<!-- guild-block:end -->", 1
    )[0]


def test_template_guild_block_matches_root_verbatim() -> None:
    """DG-407. `src/core/templates/AGENTS.md` is what `drunken-init` hands a
    new project; its pointer table must be the same table this repo's own
    AGENTS.md carries, or the two drift the moment either is edited alone."""
    root = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    template = (REPO_ROOT / "src" / "core" / "templates" / "AGENTS.md").read_text(
        encoding="utf-8"
    )

    assert _guild_block(template) == _guild_block(root)


def test_retired_md_records_agents_md_reintroduced() -> None:
    retired = (REPO_ROOT / "RETIRED.md").read_text(encoding="utf-8")
    assert "AGENTS.md" in retired
    assert "DG-390" in retired


# --- DG-396. The guild block is the one routing table; these three checks are
# the acceptance lines from the ticket. The table is already synced with the
# template (DG-407), so none of these are expected to fail against the real
# file -- they exist to catch a *future* regression. Each check is proven to
# actually detect a violation using a deliberately broken fixture below.


def _table_rows(block: str) -> list[tuple[str, str]]:
    """Parse `| situation | pick up |` data rows out of a guild block,
    skipping the header and the `|---|---|` separator."""
    rows: list[tuple[str, str]] = []
    for line in block.splitlines():
        line = line.strip()
        if not line.startswith("|") or not line.endswith("|"):
            continue
        cells = [c.strip() for c in line.strip("|").split("|")]
        if len(cells) != 2:
            continue
        if cells[0].lower() == "situation" or set(cells[0]) <= {"-"}:
            continue
        rows.append((cells[0], cells[1]))
    return rows


_AMBIGUOUS_OR = re.compile(r"`/[\w-]+`\s+or\s+`/[\w-]+`")
_AMBIGUOUS_ROLE_OR = re.compile(r"\*\*\w+\*\*\s+or\s+\*\*\w+\*\*")


def _routes_with_more_than_one_target(rows: list[tuple[str, str]]) -> list[str]:
    """A route is ambiguous when its 'pick up' cell offers two commands or
    two roles joined by a bare 'or', rather than one target (or none)."""
    violations = []
    for situation, pickup in rows:
        if _AMBIGUOUS_OR.search(pickup) or _AMBIGUOUS_ROLE_OR.search(pickup):
            violations.append(situation)
    return violations


def test_guild_block_check_catches_a_route_naming_two_targets() -> None:
    """Prove the checker used below actually detects the violation it
    claims to -- a route written as '`/foo` or `/bar`' is exactly the
    second-surface ambiguity ACCEPTANCE forbids."""
    bad_block = (
        "| situation | pick up |\n|---|---|\n| **ambiguous** | `/foo` or `/bar` |\n"
    )
    assert _routes_with_more_than_one_target(_table_rows(bad_block)) == [
        "**ambiguous**"
    ]


def test_every_route_names_exactly_one_target_or_none() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rows = _table_rows(_guild_block(text))
    assert rows, "guild block has no data rows to check"
    violations = _routes_with_more_than_one_target(rows)
    assert not violations, (
        f"route(s) name two targets joined by 'or' instead of one or none: {violations}"
    )


def test_every_role_is_reached_by_at_least_one_route() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rows = _table_rows(_guild_block(text))
    pickups = " ".join(pickup for _situation, pickup in rows)
    for role in ("manager", "worker", "reviewer"):
        assert f"**{role}**" in pickups, (
            f"no route's 'pick up' cell names the {role} role"
        )


def test_guild_block_check_catches_a_role_reached_by_no_route() -> None:
    """Same proof as above, for the role-coverage check: a block missing a
    bolded role in every pick-up cell must be flagged."""
    rows = _table_rows(
        "| situation | pick up |\n|---|---|\n| **ticket** | `/build` |\n"
    )
    pickups = " ".join(pickup for _situation, pickup in rows)
    assert "**reviewer**" not in pickups


def test_no_situation_row_outside_the_block_differs_in_wording_from_inside_it() -> None:
    """DG-396. A second 'situation -> pick up' table, or a lone row copying
    one of the block's situations with different wording, is the exact
    second-surface problem the guild block exists to cure."""
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    block = _guild_block(text)
    inside = dict(_table_rows(block))

    before, _, after = text.partition("<!-- guild-block:start -->")
    _, _, after = after.partition("<!-- guild-block:end -->")
    outside_text = before + after

    outside_rows = _table_rows(outside_text)
    for situation, pickup in outside_rows:
        if situation in inside:
            assert pickup == inside[situation], (
                f"{situation!r} is worded differently outside the guild block "
                f"than inside it:\n  inside:  {inside[situation]!r}\n"
                f"  outside: {pickup!r}"
            )

    # A second full routing table (its own header) is the same problem even
    # if no individual situation string happens to collide.
    assert outside_text.count("| situation | pick up |") == 0


def test_guild_block_check_catches_a_duplicated_situation_with_different_wording() -> (
    None
):
    """Proof for the check above: the same situation, reworded outside the
    block, must be flagged rather than silently accepted as a second table."""
    inside = dict(
        _table_rows(
            _guild_block(
                (
                    "<!-- guild-block:start -->\n"
                    "| situation | pick up |\n"
                    "|---|---|\n"
                    "| **end of day / closing a session** | `/audit`. |\n"
                    "<!-- guild-block:end -->\n"
                )
            )
        )
    )
    outside_rows = _table_rows(
        "| **end of day / closing a session** | run `/audit` whenever you feel like it |\n"
    )
    mismatches = [
        situation
        for situation, pickup in outside_rows
        if situation in inside and pickup != inside[situation]
    ]
    assert mismatches == ["**end of day / closing a session**"]
