"""DG-460: the suite must never read the operator's real project registry.

`conftest.hermetic_drunken_home` points every test's `$DRUNKEN_HOME` at a
scratch directory by default. `conftest.forbid_real_registry_access` is the
independent check that the override actually took: it fails any test whose
`ProjectRegistry` still resolves to the operator's real
`~/.drunken/projects.json`, naming the offending test in the failure.

These tests prove the guard itself works, against the real code it patches —
not by re-implementing its comparison, but by exercising
`ProjectRegistry.__init__` the way `forbid_real_registry_access` has wrapped
it and asserting on the `pytest.fail` it raises.
"""

from __future__ import annotations

from pathlib import Path

import conftest
import pytest

from core.registry import ProjectRegistry


class TestTheComparisonItself:
    """`_resolves_to_the_real_registry` is what decides "real" vs. "sandboxed".

    A test deliberately unsandboxed is simulated by comparing straight
    against `conftest._REAL_REGISTRY_PATH` — the same value the fixture
    computed from the untouched environment — never by opening it.
    """

    def test_the_operators_real_registry_path_matches(self) -> None:
        assert conftest._resolves_to_the_real_registry(conftest._REAL_REGISTRY_PATH)

    def test_a_string_form_of_the_same_path_also_matches(self) -> None:
        """`ProjectRegistry.registry_path` is a plain `str`, not a `Path`."""
        assert conftest._resolves_to_the_real_registry(
            str(conftest._REAL_REGISTRY_PATH)
        )

    def test_a_sandboxed_path_does_not_match(self, tmp_path: Path) -> None:
        assert not conftest._resolves_to_the_real_registry(tmp_path / "projects.json")


class TestTheAutouseGuardFires:
    """`forbid_real_registry_access` wraps `ProjectRegistry.__init__` for the
    whole session. This exercises that live wrapper, not a stand-in for it:
    if DG-460 ever regresses and the wrapper stops being installed, or stops
    checking the right thing, these go red.
    """

    def test_building_a_registry_at_the_real_path_fails_the_test(self) -> None:
        """A deliberately unsandboxed construction: the real path, passed
        explicitly, the way an offending call in the wild would arrive at it
        via an unset `DRUNKEN_HOME`. The guard must fail this — and name it.
        """
        with pytest.raises(pytest.fail.Exception) as excinfo:
            ProjectRegistry(str(conftest._REAL_REGISTRY_PATH))

        assert "real registry" in str(excinfo.value)
        assert "DG-460" in str(excinfo.value)

    def test_building_a_registry_at_a_sandboxed_path_is_unaffected(
        self, tmp_path: Path
    ) -> None:
        registry = ProjectRegistry(str(tmp_path / "projects.json"))
        assert registry.registry_path == str(tmp_path / "projects.json")

    def test_an_override_free_construction_is_also_unaffected(self) -> None:
        """`hermetic_drunken_home` already pointed `$DRUNKEN_HOME` at a
        scratch directory for this test, so the override-free path the guard
        is defending against never arises here in the first place."""
        registry = ProjectRegistry()
        assert not conftest._resolves_to_the_real_registry(registry.registry_path)
