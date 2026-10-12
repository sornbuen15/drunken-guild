# mypy: ignore-errors
"""DG-514 blocker A. Every one of the 16 skills (and 15 agents) the packaged ``drunken-extras``
plugin ships used to ALSO be a name on ``scripts/install/retired_skills.txt`` — they were retired
from CORE in the 2.0.0 re-scope, then re-shipped as optional extras (DG-512), and nobody removed
them from the retired list. The Python installer (``core.install``, what ``drunken-install`` the
CLI actually runs) never learned that a name can be "on the retired list" and "shipped today,
just not from core" at the same time:

* ``drunken-install status`` printed ``retired, still installed: <name>`` for every extra a user
  had just installed with ``drunken-install extras --apply``.
* ``drunken-install skills --prune`` planned to remove every one of them, and
  ``--prune --prune-apply`` would have deleted exactly what the user had just installed — the
  real, reproduced defect (not a hypothetical): see ``test_install_prune.py``'s own single-name
  version of this rule for the shell installers, which already got it right; this file is the
  Python installer's missing equivalent, at full scale.
* ``drunken-install agents`` printed ``installed here but not shipped`` for every extras agent
  for the same reason.

The fix has two layers, deliberately:

1. The 16 names are removed from ``scripts/install/retired_skills.txt`` — a name shipped today by
   drunken-extras is not retired, full stop, and the overlap is the bug. The guard test below
   fails this build if any packaged drunken-extras name (skill or agent) ever reappears there.
2. ``core.install`` also excludes every packaged drunken-extras name at the point ``_find_orphans``
   / ``status`` / ``install_agents`` classify what is installed, the same "currently shipped wins
   over retired" rule ``install_skills.sh``/``.ps1`` and ``doctor.py`` already applied — belt and
   suspenders, so a transient re-addition to the list (caught by the guard test before merge, but
   not yet reverted) still cannot delete anything at runtime.
"""

from __future__ import annotations

from pathlib import Path

import pytest

from core import install, install_extras

REPO = Path(__file__).resolve().parent.parent


def test_no_packaged_extras_name_is_on_the_retired_list() -> None:
    """The guard DG-514 asked for: a name the packaged drunken-extras plugin ships — skill or
    agent — must never appear on scripts/install/retired_skills.txt again. That overlap is
    exactly what let `--prune --prune-apply` delete what `drunken-install extras --apply` had
    just installed."""
    retired = install.retired_names()
    extras_skills = set(install_extras.extras_skill_names())
    extras_agents = set(install_extras.extras_agent_names())

    assert extras_skills, "fixture premise: drunken-extras must ship at least one skill"
    assert extras_agents, "fixture premise: drunken-extras must ship at least one agent"

    overlap = (extras_skills | extras_agents) & retired
    assert not overlap, (
        f"{sorted(overlap)} are shipped by the packaged drunken-extras plugin AND on "
        "scripts/install/retired_skills.txt at the same time — exactly the DG-514 data-loss bug. "
        "Remove them from retired_skills.txt."
    )


class TestPackagedExtrasNamesAreNeverRetiredOrOrphaned:
    """End-to-end: install core + extras into temp targets, then every status/prune surface must
    treat every extras name as shipped — never retired, never unrecognised, never pruned."""

    @pytest.fixture()
    def targets(self, tmp_path: Path) -> tuple[Path, Path]:
        skills_target = tmp_path / "skills"
        agents_target = tmp_path / "agents"
        install.install_skills(skills_target, apply=True)
        install.install_agents(agents_target, skills_target, apply=True)
        install_extras.install_extras(skills_target, agents_target, apply=True)
        return skills_target, agents_target

    def test_status_prints_no_retired_line_for_any_extra(self, targets, capsys):
        skills_target, agents_target = targets
        report = install.status(skills_target, agents_target)

        extras_skills = set(install_extras.extras_skill_names())
        assert not (set(report.retired_installed) & extras_skills), (
            f"{sorted(set(report.retired_installed) & extras_skills)} were reported "
            "'retired, still installed' even though drunken-install extras --apply had just "
            "installed them"
        )

        install._print_status(report)
        out = capsys.readouterr().out
        for name in extras_skills:
            assert f"retired, still installed: {name}" not in out

    def test_prune_plan_lists_nothing_for_any_extras_skill(self, targets):
        skills_target, agents_target = targets
        result = install.install_skills(
            skills_target, apply=False, prune=True, prune_apply=False
        )

        extras_skills = set(install_extras.extras_skill_names())
        retired_orphan_names = {o.name for o in result.orphans if o.kind == "retired"}
        assert not (retired_orphan_names & extras_skills), (
            f"{sorted(retired_orphan_names & extras_skills)} were planned for removal by "
            "--prune --prune-apply even though they are the packaged drunken-extras skills"
        )

    def test_prune_apply_removes_none_of_the_installed_extras(self, targets):
        skills_target, agents_target = targets
        extras_skills = set(install_extras.extras_skill_names())
        before = {p.name for p in skills_target.iterdir() if p.is_dir()}
        assert extras_skills <= before, (
            "fixture premise: extras must actually be on disk"
        )

        install.install_skills(skills_target, apply=True, prune=True, prune_apply=True)

        after = {p.name for p in skills_target.iterdir() if p.is_dir()}
        assert extras_skills <= after, (
            f"{sorted(extras_skills - after)} were deleted by --prune --prune-apply — the exact "
            "data loss this ticket exists to prevent"
        )

    def test_agents_report_prints_no_not_shipped_line_for_any_extras_agent(
        self, targets, capsys
    ):
        skills_target, agents_target = targets
        result = install.install_agents(agents_target, skills_target, apply=False)

        extras_agents = set(install_extras.extras_agent_names())
        assert not (set(result.orphans) & extras_agents), (
            f"{sorted(set(result.orphans) & extras_agents)} were reported as agent orphans even "
            "though they are the packaged drunken-extras agents"
        )

        install._print_agents(result)
        out = capsys.readouterr().out
        for name in extras_agents:
            assert f"installed here but not shipped (left in place): {name}" not in out


def test_mutation_without_the_extras_exclusion_the_above_would_fail(tmp_path):
    """Not a permanent mutation — demonstrates that the tests above actually distinguish the
    fixed behaviour from the broken one, by calling the lower-level helper the pre-fix code used,
    with the extras exclusion argument it never had. retired_skills.txt no longer overlaps with
    drunken-extras (layer 1 of the fix), so without the exclusion argument these would now be
    reported "unrecognised" rather than "retired" — one layer of the original bug is gone either
    way, but they would still show up as orphans at all, which is what the exclusion argument
    (layer 2, belt-and-suspenders) exists to prevent."""
    skills_target = tmp_path / "skills"
    agents_target = tmp_path / "agents"
    install.install_skills(skills_target, apply=True)
    install_extras.install_extras(skills_target, agents_target, apply=True)

    folders = install._skill_folders(install.packaged_skills_dir())
    pre_fix_orphans = install._find_orphans(
        skills_target,
        set(folders),
        install._external_names(install.packaged_skills_dir()),
        install.retired_names(),
        # the one argument the fix added — omitted here, reproducing the pre-fix call
    )
    extras_skills = set(install_extras.extras_skill_names())
    pre_fix_orphan_names = {o.name for o in pre_fix_orphans}
    assert pre_fix_orphan_names & extras_skills, (
        "sanity check on the mutation itself: calling _find_orphans without the extras "
        "exclusion argument should still report every installed extras skill as an orphan of "
        "some kind, proving the exclusion argument is what the real calls above depend on"
    )

    fixed_orphans = install._find_orphans(
        skills_target,
        set(folders),
        install._external_names(install.packaged_skills_dir()),
        install.retired_names(),
        install._extras_skill_names(),
    )
    fixed_orphan_names = {o.name for o in fixed_orphans}
    assert not (fixed_orphan_names & extras_skills), (
        "with the exclusion argument restored, no extras skill should be an orphan at all"
    )
