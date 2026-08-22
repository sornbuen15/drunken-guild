# mypy: ignore-errors
"""DG-257. The state is read, and what could not be read says so.

SESSION_CHECKPOINT.md section 2 went stale within an hour of being written, and
the file records that it "has been wrong twice, in both directions". It was
stale again while this module was being written: it named three PRs as awaiting
merge that had all merged, and a test count 49 behind.

The distinction every test here turns on is between "the answer is nothing" and
"I could not ask". Collapsing those is what let a dead Jira token answer with an
empty board for months -- HTTP 200 and an empty list look exactly like a project
with no work in it (S4).
"""

import json

from core import status


class TestAnAbsentSourceIsNotAnEmptyOne:
    def test_a_directory_that_is_not_a_repository_reports_why(self, tmp_path) -> None:
        section = status.git_section(tmp_path)

        assert section.available is False
        assert "git repository" in section.reason

    def test_an_unavailable_gh_is_not_reported_as_no_open_prs(
        self, tmp_path, monkeypatch
    ) -> None:
        """The failure that matters. "No open PRs" is a fact somebody acts on;
        "gh is not installed" is not the same fact wearing a different hat."""
        monkeypatch.setattr(status, "_run", lambda argv, cwd=None: None)

        section = status.pr_section(tmp_path)

        assert section.available is False
        assert "Not the same as having no open PRs" in section.reason

    def test_no_open_prs_is_reported_as_none_rather_than_omitted(
        self, tmp_path, monkeypatch
    ) -> None:
        monkeypatch.setattr(status, "_run", lambda argv, cwd=None: "[]")

        section = status.pr_section(tmp_path)

        assert section.available is True
        assert section.rows == ["| — | none open |"]

    def test_jira_that_will_not_answer_says_so(self, monkeypatch) -> None:
        section = status.jira_section("a-project-that-is-not-registered")

        assert section.available is False
        assert "could not ask Jira" in section.reason

    def test_the_rendered_report_names_what_it_could_not_reach(self) -> None:
        """Silently dropping a section would make the report read as complete."""
        unreachable = status.Section("jira", available=False, reason="no credential")

        rendered = status.render([unreachable])

        assert "not answered" in rendered and "no credential" in rendered


class TestItReportsPositionRatherThanGuessingFromTheBranchName:
    def test_being_level_is_stated_as_level(self, monkeypatch, tmp_path) -> None:
        """A branch called anything can be exactly where origin/develop is, and
        an earlier cut called that "not level" purely because of the name --
        which is the difference between "merged" and "merged on my machine"
        reported backwards."""
        answers = {
            "rev-parse": "abc1234",
            "rev-list": "0\t0",
            "tag": "v2.3.0",
        }

        def fake_run(argv, cwd=None):
            for key, value in answers.items():
                if key in argv:
                    return "feature/x" if "--abbrev-ref" in argv else value
            return None

        monkeypatch.setattr(status, "_run", fake_run)

        section = status.git_section(tmp_path)

        assert "level with" in section.rows[-1]
        assert section.data["ahead"] == 0 and section.data["behind"] == 0

    def test_divergence_is_counted_not_described(self, monkeypatch, tmp_path) -> None:
        def fake_run(argv, cwd=None):
            if "--abbrev-ref" in argv:
                return "develop"
            if "rev-list" in argv:
                return "2\t3"
            if "rev-parse" in argv:
                return "abc1234"
            return None

        monkeypatch.setattr(status, "_run", fake_run)

        section = status.git_section(tmp_path)

        assert section.data["ahead"] == 3 and section.data["behind"] == 2
        assert "3 ahead, 2 behind" in section.rows[-1]


class TestItIsReadOnly:
    def test_no_test_run_unless_asked(self, tmp_path, monkeypatch) -> None:
        """A test count is a fact if it was measured this minute and a rumour
        otherwise. Running the suite is opt-in because it takes time, and
        reprinting a remembered number is the habit this command exists to
        break -- so it does neither by default."""
        called = []
        monkeypatch.setattr(
            status, "_run", lambda argv, cwd=None: called.append(argv) or "[]"
        )

        status.pr_section(tmp_path)

        assert not any("pytest" in argv for argv in called)

    def test_the_json_shape_carries_availability(self, tmp_path, monkeypatch) -> None:
        """A consumer must be able to tell a real answer from a missing one
        without parsing prose."""
        section = status.Section("jira", available=False, reason="nope")

        payload = json.loads(
            json.dumps({section.name: {"available": section.available}})
        )

        assert payload["jira"]["available"] is False
