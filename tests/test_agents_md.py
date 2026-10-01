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


_BACKTICK_SPAN = re.compile(r"`[^`]+`")
_BOLD_SPAN = re.compile(r"\*\*[^*]+\*\*")
_OR_OR_SLASH = re.compile(r"\bor\b|\s/\s", re.IGNORECASE)


def _clauses(cell: str) -> list[str]:
    """Split a pick-up cell on sentence-ending periods. A chain --
    '`/prd` -> `/clarify` -> ..., in that order' -- is one clause naming one
    route; an alternative is named *within* a single clause, whatever words
    carry it.

    A period inside a backtick span (`skills/INDEX.md`, `SKILL.md`) is not a
    sentence boundary, so backtick spans are masked before splitting and
    restored after -- otherwise a path's own '.' would cut a target in half
    and hide it from the distinct-target count on either side.
    """
    masked_spans: list[str] = []

    def _mask(match: re.Match[str]) -> str:
        masked_spans.append(match.group(0))
        return f"\0{len(masked_spans) - 1}\0"

    masked = _BACKTICK_SPAN.sub(_mask, cell)

    def _unmask(clause: str) -> str:
        for index, span in enumerate(masked_spans):
            clause = clause.replace(f"\0{index}\0", span)
        return clause

    return [_unmask(c.strip()) for c in masked.split(".") if c.strip()]


def _distinct_targets(clause: str) -> set[str]:
    """A target is a backtick span (a command or a path) or a bold span (a
    role). Counting *distinct* mentions, not occurrences, so a clause that
    names the same target twice does not look like two targets."""
    return set(_BACKTICK_SPAN.findall(clause)) | set(_BOLD_SPAN.findall(clause))


def _routes_naming_more_than_one_target(rows: list[tuple[str, str]]) -> list[str]:
    """A route names more than one target when a single clause of its
    'pick up' cell names two or more distinct targets *and* joins them with
    a bare 'or' or a ' / ' alternative -- no matter how that is worded, so
    rewording a route as 'the **manager** role or the **worker** role',
    '`skills/INDEX.md` or ask the **manager**', or a comma-led
    '`/git-workflow`, or ask the **manager**' cannot dodge it.

    A chain naming several targets in order ('`/prd`, `/clarify`, ..., in
    that order', '... via ...') is not flagged: it never joins them with
    'or' or '/'. A clause enumerating *conditions* for one target ('`/replan`
    when a requirement is added, cut or changed') is not flagged either: its
    'or' sits in a clause with exactly one target.
    """
    violations = []
    for situation, pickup in rows:
        for clause in _clauses(pickup):
            if _OR_OR_SLASH.search(clause) and len(_distinct_targets(clause)) >= 2:
                violations.append(situation)
                break
    return violations


def test_guild_block_check_catches_two_roles_joined_by_bare_or() -> None:
    """Fed through the real checker, not a bespoke fixture: rewording the
    old 'role or role' attack as full phrases must still be caught."""
    rows = [("**situation**", "the **manager** role or the **worker** role")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_a_path_and_a_role_joined_by_or() -> None:
    """A mixed path/role alternative -- the kind of wording that slipped
    past a narrower, backtick-only pattern -- must still be caught."""
    rows = [("**situation**", "`skills/INDEX.md` or ask the **manager**")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_a_comma_led_alternative() -> None:
    """A comma-led alternative ('X, or Y') is the same ambiguity with a
    comma in front of the 'or'; it must still be caught."""
    rows = [("**situation**", "`/git-workflow`, or ask the **manager**")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_every_route_names_exactly_one_target_or_none() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rows = _table_rows(_guild_block(text))
    assert rows, "guild block has no data rows to check"
    violations = _routes_naming_more_than_one_target(rows)
    assert not violations, (
        f"route(s) name an alternative instead of one target or none: {violations}"
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


def _outside_block_text(text: str) -> str:
    before, _, after = text.partition("<!-- guild-block:start -->")
    _, _, after = after.partition("<!-- guild-block:end -->")
    return before + after


def _duplicate_situation_mismatches(text: str) -> list[str]:
    """Rows outside a file's guild block that repeat a situation from
    inside it with different wording, plus a second full routing table
    (its own header), are both the second-surface problem the block exists
    to cure. Returns the offending situations; `'<second table header>'`
    stands in for a second table found with no individually colliding
    situation string."""
    inside = dict(_table_rows(_guild_block(text)))
    outside_text = _outside_block_text(text)
    outside_rows = _table_rows(outside_text)

    mismatches = [
        situation
        for situation, pickup in outside_rows
        if situation in inside and pickup != inside[situation]
    ]
    if "| situation | pick up |" in outside_text:
        mismatches.append("<second table header>")
    return mismatches


def test_no_situation_row_outside_the_root_block_differs_in_wording_from_inside_it() -> (
    None
):
    """DG-396. A second 'situation -> pick up' table, or a lone row copying
    one of the root block's situations with different wording, is the exact
    second-surface problem the guild block exists to cure."""
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    assert _duplicate_situation_mismatches(text) == []


def test_no_situation_row_outside_the_template_block_differs_in_wording_from_inside_it() -> (
    None
):
    """Same guarantee for `src/core/templates/AGENTS.md` (DG-407): the
    template is what `drunken-init` hands a new project, so it is just as
    able to grow a second, drifting table as the root file is."""
    template = (REPO_ROOT / "src" / "core" / "templates" / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    assert _duplicate_situation_mismatches(template) == []


def test_guild_block_check_catches_a_duplicated_situation_with_different_wording() -> (
    None
):
    """Proof for the checks above, fed through the real checker: splice a
    reworded duplicate of a real situation into a scratch copy of the
    template, outside the markers, and confirm it is flagged."""
    template = (REPO_ROOT / "src" / "core" / "templates" / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    mutated = template + (
        "\n\n| **end of day / closing a session** |"
        " run `/audit` whenever you feel like it |\n"
    )
    assert _duplicate_situation_mismatches(mutated) == [
        "**end of day / closing a session**"
    ]


def test_guild_block_check_catches_a_second_routing_table() -> None:
    """Same proof, for a second table that introduces no colliding
    situation string at all -- still a second surface, still flagged."""
    template = (REPO_ROOT / "src" / "core" / "templates" / "AGENTS.md").read_text(
        encoding="utf-8"
    )
    mutated = template + "\n\n| situation | pick up |\n|---|---|\n| **x** | `/y` |\n"
    assert _duplicate_situation_mismatches(mutated) == ["<second table header>"]
