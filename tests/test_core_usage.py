# mypy: ignore-errors
"""Counting what a run actually cost — DG-95.

The ticket's own words: there is no way to measure or verify token efficiency,
and it is *"needed before any claim of 'this saves tokens' can be substantiated
with data rather than assumption."* This repo has made that claim more than
once — `minify_issues` exists for it, DG-227 was cut for it — and nothing has
ever checked one.

Nothing new is instrumented, because nothing needs to be. The host already
writes per-message usage to its transcripts, and every record carries the git
branch, which under this project's own convention carries a ticket key. So cost
per ticket is a read, not a measurement.

Two things these tests are mostly about, both of which are ways to produce a
confident wrong number:

* **Another project's records must not be counted as this one's.** The
  directory name is a guess at a private naming scheme; `cwd` inside each
  record is the authority.
* **An unknown model prices at `None`, never `0.0`.** A zero reads as "this
  was free" and is indistinguishable from a real answer — the S4 shape, where
  a dead credential returned an empty list instead of an error.
"""

from __future__ import annotations

import json

import pytest

from core import usage


class TestFindingThisProjectsRecords:
    def test_the_directory_name_is_derived_the_way_the_host_writes_it(self) -> None:
        """`/Users/you/Projects/drunken-guild` is stored as
        `-Users-you-Projects-drunken-guild`: every character that is not
        alphanumeric becomes a dash, the leading slash included."""
        assert (
            usage.slug_for("/Users/you/Projects/drunken-guild")
            == "-Users-you-Projects-drunken-guild"
        )

    def test_a_worktree_of_the_same_project_is_a_different_directory(self) -> None:
        """Worktrees get their own transcript directory, and work done in one
        is still this project's cost. The slug is a prefix, not an equality."""
        assert usage.slug_for(
            "/Users/you/Projects/drunken-guild/.claude/worktrees/x"
        ).startswith(usage.slug_for("/Users/you/Projects/drunken-guild"))

    def test_records_from_another_project_are_not_counted_as_this_one(
        self, tmp_path
    ) -> None:
        """The guard that stops a number being confidently wrong. A directory
        whose name merely starts the same way still has to prove itself by the
        `cwd` its records carry."""
        root = tmp_path / "projects"
        mine = root / "-tmp-proj"
        theirs = root / "-tmp-proj-other"
        for d in (mine, theirs):
            d.mkdir(parents=True)
        _write(mine / "a.jsonl", [_rec(cwd="/tmp/proj", output=10)])
        _write(theirs / "b.jsonl", [_rec(cwd="/tmp/proj-other", output=999)])

        records = list(usage.iter_records(root, "/tmp/proj"))

        assert [r.usage.output for r in records] == [10]

    def test_a_worktree_under_the_project_is_counted(self, tmp_path) -> None:
        root = tmp_path / "projects"
        wt = root / "-tmp-proj--claude-worktrees-x"
        wt.mkdir(parents=True)
        _write(wt / "a.jsonl", [_rec(cwd="/tmp/proj/.claude/worktrees/x", output=7)])

        assert [r.usage.output for r in usage.iter_records(root, "/tmp/proj")] == [7]

    def test_a_missing_root_reads_as_no_records_rather_than_raising(
        self, tmp_path
    ) -> None:
        """A fresh machine has no transcripts. Principle 8: the failure has to
        be a readable answer, not an exception from inside a tool call."""
        assert list(usage.iter_records(tmp_path / "nope", "/tmp/proj")) == []


class TestReadingATranscript:
    def test_lines_that_are_not_json_are_skipped_not_fatal(self, tmp_path) -> None:
        """A transcript is another tool's private format, appended to while it
        is being read. A half-written last line must not lose the file."""
        root = tmp_path / "projects"
        d = root / "-tmp-proj"
        d.mkdir(parents=True)
        (d / "a.jsonl").write_text(
            json.dumps(_rec(cwd="/tmp/proj", output=5))
            + "\n"
            + "{not json\n"
            + json.dumps(_rec(cwd="/tmp/proj", output=6))
            + '\n{"half": ',
            encoding="utf-8",
        )

        assert sorted(
            r.usage.output for r in usage.iter_records(root, "/tmp/proj")
        ) == [
            5,
            6,
        ]

    def test_records_with_no_usage_are_ignored(self, tmp_path) -> None:
        """Most records are prompts, attachments and titles. Only the ones that
        cost something count."""
        root = tmp_path / "projects"
        d = root / "-tmp-proj"
        d.mkdir(parents=True)
        _write(
            d / "a.jsonl",
            [
                {"type": "user", "cwd": "/tmp/proj", "message": {"content": "hi"}},
                _rec(cwd="/tmp/proj", output=3),
            ],
        )

        assert len(list(usage.iter_records(root, "/tmp/proj"))) == 1

    def test_a_missing_usage_field_counts_as_zero_not_as_absent(self) -> None:
        """`input_tokens` is sometimes absent on a cached turn. Absent means
        none were billed, which is a number."""
        parsed = usage.Usage.from_payload({"output_tokens": 4})
        assert (parsed.input, parsed.output, parsed.cache_read) == (0, 4, 0)

    def test_cache_tokens_are_counted_and_named_separately(self) -> None:
        """They dominate: 2.0 billion cache reads against 6.4 million output
        tokens on this project. Folding them into one total would hide the only
        number a caching change moves."""
        parsed = usage.Usage.from_payload(
            {
                "input_tokens": 1,
                "output_tokens": 2,
                "cache_read_input_tokens": 4,
                "cache_creation_input_tokens": 8,
            }
        )
        assert parsed.total == 15
        assert (parsed.cache_read, parsed.cache_creation) == (4, 8)


class TestAttributingWorkToATicket:
    def test_a_feature_branch_names_its_ticket(self) -> None:
        assert usage.ticket_of("feature/DG-251-board-backlog") == "DG-251"

    def test_every_branch_prefix_this_project_uses_works(self) -> None:
        for branch in ("bugfix/DG-9-x", "chore/DG-238-y", "docs/DG-249-z"):
            assert usage.ticket_of(branch) is not None

    def test_a_trunk_branch_has_no_ticket_rather_than_a_wrong_one(self) -> None:
        """`develop` carries the largest share of records. Inventing a ticket
        for it would put a real number under a made-up heading."""
        assert usage.ticket_of("develop") is None
        assert usage.ticket_of("main") is None
        assert usage.ticket_of(None) is None

    def test_a_branch_named_only_for_the_ticket_still_resolves(self) -> None:
        assert usage.ticket_of("feature/DG-90") == "DG-90"

    def test_the_key_is_normalised_to_the_way_jira_writes_it(self) -> None:
        assert usage.ticket_of("feature/dg-251-x") == "DG-251"


class TestRollingUp:
    RECORDS = [
        usage.Record(
            "s1",
            "2026-08-16T01:00:00Z",
            "feature/DG-251-x",
            "opus",
            usage.Usage(1, 2, 3, 4),
        ),
        usage.Record(
            "s1",
            "2026-08-16T02:00:00Z",
            "feature/DG-251-x",
            "opus",
            usage.Usage(1, 2, 3, 4),
        ),
        usage.Record(
            "s2", "2026-08-16T03:00:00Z", "develop", "sonnet", usage.Usage(10, 0, 0, 0)
        ),
    ]

    def test_it_sums_by_the_key_asked_for(self) -> None:
        rolled = usage.roll_up(self.RECORDS, key="ticket")
        assert rolled["DG-251"].usage.total == 20
        assert rolled["(none)"].usage.total == 10

    def test_sessions_are_counted_distinctly_not_per_message(self) -> None:
        """Two messages in one session is one run. Counting messages instead
        would make a chatty session look like many."""
        rolled = usage.roll_up(self.RECORDS, key="ticket")
        assert (rolled["DG-251"].sessions, rolled["DG-251"].messages) == (1, 2)

    def test_every_model_that_contributed_is_named(self) -> None:
        """A cheap model and an expensive one are not interchangeable, so a
        total with the mix hidden cannot be compared against another total."""
        assert usage.roll_up(self.RECORDS, key="ticket")["DG-251"].models == {"opus"}

    def test_the_span_of_a_rollup_is_kept(self) -> None:
        rolled = usage.roll_up(self.RECORDS, key="ticket")["DG-251"]
        assert rolled.first.endswith("01:00:00Z") and rolled.last.endswith("02:00:00Z")

    def test_it_rolls_up_by_branch_session_and_model_too(self) -> None:
        for key in ("branch", "session", "model"):
            assert usage.roll_up(self.RECORDS, key=key)


class TestCostIsNeverInvented:
    """Rates are an operator input, not a constant in this repo.

    Prices change, differ by contract, and are not knowable from inside a
    process. A table hardcoded here would keep returning numbers long after it
    stopped being true, and every one of them would look authoritative.
    """

    RATES = {
        "opus": {
            "input": 15.0,
            "output": 75.0,
            "cache_read": 1.5,
            "cache_creation": 18.75,
        }
    }

    def test_an_unpriced_model_costs_none_rather_than_zero(self) -> None:
        """Zero reads as "this was free" and is indistinguishable from a real
        answer. `None` reads as "nobody told me the rate"."""
        assert usage.cost_usd(usage.Usage(1, 1, 1, 1), "sonnet", self.RATES) is None

    def test_no_rates_at_all_costs_none_everywhere(self) -> None:
        assert usage.cost_usd(usage.Usage(1, 1, 1, 1), "opus", {}) is None

    def test_a_priced_model_is_charged_per_million_tokens(self) -> None:
        cost = usage.cost_usd(
            usage.Usage(
                input=1_000_000, output=1_000_000, cache_read=0, cache_creation=0
            ),
            "opus",
            self.RATES,
        )
        assert cost == pytest.approx(90.0)

    def test_cache_reads_are_charged_at_their_own_rate(self) -> None:
        """The point of pricing cache separately: it is 99.9% of the tokens
        here, and at the input rate the total would be off by two orders of
        magnitude."""
        cost = usage.cost_usd(
            usage.Usage(input=0, output=0, cache_read=1_000_000, cache_creation=0),
            "opus",
            self.RATES,
        )
        assert cost == pytest.approx(1.5)

    def test_a_partial_rate_table_still_refuses_to_guess_the_rest(self) -> None:
        """A model priced for input only is not priced. Filling the gap with a
        zero would understate every answer it appears in."""
        assert (
            usage.cost_usd(usage.Usage(1, 1, 1, 1), "opus", {"opus": {"input": 15.0}})
            is None
        )

    def test_rates_load_from_a_file_and_a_missing_one_is_not_an_error(
        self, tmp_path
    ) -> None:
        path = tmp_path / "rates.json"
        assert usage.load_rates(path) == {}
        path.write_text(json.dumps(self.RATES), encoding="utf-8")
        assert usage.load_rates(path)["opus"]["output"] == 75.0

    def test_an_unreadable_rates_file_reads_as_no_rates(self, tmp_path) -> None:
        """Principle 4: a corrupt file reads as empty rather than raising, and
        the report then shows tokens with no cost — which is visibly missing
        rather than silently wrong."""
        path = tmp_path / "rates.json"
        path.write_text("{ not json", encoding="utf-8")
        assert usage.load_rates(path) == {}


class TestTheReportSaysWhatItCannotSee:
    def test_it_names_the_host_whose_records_it_read(self, tmp_path) -> None:
        """Antigravity's usage lives under a directory CLAUDE.md forbids
        touching, so this counts one of the two agents working this repo. A
        total presented without that caveat would be read as the whole bill."""
        report = usage.build_report(tmp_path / "nope", "/tmp/proj", key="ticket")
        assert "claude" in report["source"].lower()
        assert report["covers"]

    def test_an_empty_report_is_still_a_valid_report(self, tmp_path) -> None:
        report = usage.build_report(tmp_path / "nope", "/tmp/proj", key="ticket")
        assert report["rows"] == [] and report["totals"]["total"] == 0


def _rec(cwd: str, output: int = 0, **kw) -> dict:
    return {
        "type": "assistant",
        "cwd": cwd,
        "sessionId": kw.get("session", "s1"),
        "timestamp": kw.get("timestamp", "2026-08-16T00:00:00Z"),
        "gitBranch": kw.get("branch", "develop"),
        "message": {
            "model": kw.get("model", "claude-opus-5"),
            "usage": {"output_tokens": output},
        },
    }


def _write(path, records) -> None:
    path.write_text("\n".join(json.dumps(r) for r in records) + "\n", encoding="utf-8")
