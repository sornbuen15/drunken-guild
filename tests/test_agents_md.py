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
_BARE_OR = re.compile(r"\bor\b", re.IGNORECASE)
_SLASH_ALTERNATIVE = re.compile(r"\s/\s")


def _sentence_ending_period_indices(cell: str) -> list[int]:
    """Indices of '.' in the cell, ignoring a period inside a backtick span
    (`skills/INDEX.md`, `SKILL.md`) -- that period ends a filename, not a
    sentence. Masking preserves length and position so the indices line up
    with the real cell."""
    masked = _BACKTICK_SPAN.sub(lambda m: "x" * len(m.group(0)), cell)
    return [i for i, ch in enumerate(masked) if ch == "."]


def _routes_naming_more_than_one_target(rows: list[tuple[str, str]]) -> list[str]:
    """Flags a pick-up cell for exactly three literal things, checked on
    the WHOLE cell with no clause splitting and no distinct-target
    counting:

    - a bare word 'or' anywhere in the cell, in any case ('or', 'OR', 'Or');
    - a ' / ' alternative (a slash with a plain space on each side);
    - a sentence-ending period anywhere except the cell's own last
      character, i.e. more than one sentence (zero periods is fine --
      nothing to end a second sentence with).

    This catches the common shapes an alternative gets written in --
    across a sentence boundary, a semicolon before 'or', 'OR' in caps, a
    comma-led 'or', 'either X or Y', a bare ' / ' -- because all of them
    still spell the literal word 'or' or ' / ', or still split the cell
    into more than one sentence.

    It is still a regex over prose, not a parser, and it does NOT catch
    every way to write "pick one of these": a unicode slash ('／'), an
    escaped pipe inside the table cell, a lone semicolon or dash standing
    in for 'or' with no word there at all, a single-character ellipsis, or
    a synonym ('Run `/build` otherwise ask the **manager**.') all read as
    clean. Closing those needs either a much larger pattern or a markdown
    parser, which is out of scope for this ticket; the Boss's own reading
    of the table at review time remains the real guard against those, not
    this function.

    A chain naming several targets in order ('`/prd` -> `/clarify` -> ...,
    in that order') is not flagged: it is one sentence and never uses the
    word 'or' or ' / '. There is no carve-out for a legitimate 'or' -- a
    cell that needs one is reworded instead (see AGENTS.md itself).
    """
    violations = []
    for situation, pickup in rows:
        cell = pickup.strip()
        if _BARE_OR.search(cell):
            violations.append(situation)
            continue
        if _SLASH_ALTERNATIVE.search(cell):
            violations.append(situation)
            continue
        periods = _sentence_ending_period_indices(cell)
        if periods and (len(periods) > 1 or periods[-1] != len(cell) - 1):
            violations.append(situation)
    return violations


def test_guild_block_check_catches_or_across_a_sentence_boundary() -> None:
    """Fed through the real checker, not a bespoke fixture: moving the
    alternative to its own sentence must still be caught."""
    rows = [("**situation**", "Run `/build`. Or ask the **manager**.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_or_between_two_role_sentences() -> None:
    rows = [("**situation**", "Ask the **manager**. Or the **reviewer**.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_or_at_the_end_of_a_clause() -> None:
    rows = [("**situation**", "Run `/build` or. Ask the **manager**.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_a_semicolon_led_alternative() -> None:
    rows = [("**situation**", "Run `/build`; or ask the **manager**.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_uppercase_or() -> None:
    rows = [("**situation**", "Run `/build` OR ask the **manager**.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_a_path_and_a_role_joined_by_or() -> None:
    rows = [("**situation**", "`skills/INDEX.md` or ask the **manager**.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_a_comma_led_alternative() -> None:
    rows = [("**situation**", "`/git-workflow`, or ask the **manager**.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_either_or() -> None:
    rows = [("**situation**", "Run either `/prd` or `/clarify`.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_a_slash_alternative() -> None:
    rows = [("**situation**", "Run `/build` / `/replan`.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_guild_block_check_catches_two_sentences_with_no_or_at_all() -> None:
    """The period rule stands on its own: two sentences are two sentences
    whether or not either one names an alternative."""
    rows = [("**situation**", "Run `/build`. Then open the pull request.")]
    assert _routes_naming_more_than_one_target(rows) == ["**situation**"]


def test_every_route_names_exactly_one_target_or_none() -> None:
    text = (REPO_ROOT / "AGENTS.md").read_text(encoding="utf-8")
    rows = _table_rows(_guild_block(text))
    assert rows, "guild block has no data rows to check"
    violations = _routes_naming_more_than_one_target(rows)
    assert not violations, (
        f"route(s) name an alternative, or more than one sentence, instead "
        f"of one target or none: {violations}"
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
