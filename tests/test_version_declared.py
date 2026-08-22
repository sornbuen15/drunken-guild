# mypy: ignore-errors
"""DG-256. The declared version must not be behind the newest release tag.

pyproject.toml pins 2.1.0. `v2.3.0` is tagged and released, and so was v2.2.0
before it -- neither bumped the declaration. So `drunken-doctor` reports
`version.drunken-guild 2.1.0`, and so does the installed tool env.

Why that is worse than a wrong number: DG-252 built a check so the deployment
can be asked what it is. Comparing checkout against deployment gives 2.1.0 on
both and concludes they agree, which is exactly the drift the check exists to
expose. A version string that lies defeats the instrument built to catch lying.

The comparison is a pure function, tested with values rather than with the
repository. Two reasons, and the second is from the checkpoint's own list of
ways running things can lie: CI checks out with `actions/checkout@v4` at the
default depth, which fetches no tags at all, and a test that reads them would
be green here and red there -- the DG-252 mistake, where an assertion held only
on a machine that had a registry.
"""

import subprocess

import pytest

from core import doctor


class TestTheComparisonItself:
    def test_behind_the_newest_tag_is_a_failure(self) -> None:
        """The state of this repository today, expressed as values."""
        status, detail = doctor.version_verdict("2.1.0", "v2.3.0")

        assert status == "fail"
        assert "2.1.0" in detail and "2.3.0" in detail

    def test_matching_the_newest_tag_is_fine(self) -> None:
        status, _ = doctor.version_verdict("2.3.0", "v2.3.0")

        assert status == "ok"

    def test_ahead_of_the_newest_tag_is_fine(self) -> None:
        """Normal development after a release: the declaration is bumped first
        and the tag catches up. Flagging this would make the check noise, and a
        check that cries wolf is one nobody reads."""
        status, _ = doctor.version_verdict("2.4.0", "v2.3.0")

        assert status == "ok"

    def test_no_declaration_is_a_skip(self) -> None:
        """An installed deployment has no pyproject to read, and saying nothing
        is the honest answer -- it genuinely cannot see the declaration."""
        status, _ = doctor.version_verdict(None, "v2.3.0")

        assert status == "skip"

    def test_no_tag_is_a_skip_not_a_failure(self) -> None:
        """A fresh clone, a shallow CI checkout, or a source tarball has no
        tags. "We could not ask" and "the answer is bad" must not collapse into
        each other -- the same distinction BoardProfile.known draws."""
        status, _ = doctor.version_verdict("2.1.0", None)

        assert status == "skip"

    def test_an_unparseable_version_skips_rather_than_guessing(self) -> None:
        """A tag that is not a version number is somebody else's convention,
        not a finding about ours."""
        status, _ = doctor.version_verdict("2.1.0", "nightly")

        assert status == "skip"

    @pytest.mark.parametrize(  # type: ignore[misc]
        "declared, tag",
        [("2.10.0", "v2.9.0"), ("2.3.1", "v2.3.0"), ("10.0.0", "v9.9.9")],
    )
    def test_it_compares_numerically_not_as_text(self, declared, tag) -> None:
        """ "2.10.0" < "2.9.0" as strings. Every one of these would be reported
        as behind by a string comparison."""
        status, _ = doctor.version_verdict(declared, tag)

        assert status == "ok", f"{declared} is not behind {tag}"


class TestAgainstTheRepositoryItself:
    def test_the_declared_version_is_not_behind_the_newest_tag(self) -> None:
        """The ticket's acceptance, run against the real tree.

        Skipped rather than failed where tags are unavailable, so CI's shallow
        checkout reports nothing instead of reporting the wrong thing.
        """
        try:
            tags = subprocess.run(
                ["git", "tag", "--sort=-v:refname"],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            pytest.skip("git is not available here")

        newest = next(iter(tags.stdout.split()), None)
        if not newest:
            pytest.skip("no tags in this checkout (shallow clone or source tarball)")

        declared = doctor.declared_version()
        if declared is None:
            pytest.skip(
                "no pyproject.toml visible from here (installed, not a checkout)"
            )

        status, detail = doctor.version_verdict(declared, newest)

        assert status != "fail", detail
