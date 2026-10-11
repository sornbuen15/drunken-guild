"""Shared pytest configuration.

The `e2e` tests talk to the real Jira instance and **create real tickets**. The
marker was added with the comment "so it doesn't run on standard unit test runs
unless requested" — but nothing ever acted on it, so every plain `pytest` run
filed two more tickets into the live DG project. DG-169 through DG-223 are the
accumulated result.

Two things stop that now. `pyproject.toml`'s addopts deselects `e2e` by default,
which is what the marker always meant. And the hook below skips those tests when
credentials are absent rather than letting them fail with a bare
"Missing credentials" -- which is what CI hit, since CI has no `.env`.

Run them deliberately, against a project you are willing to write to:

    pytest -m e2e
"""

from __future__ import annotations

import importlib
import sys
from pathlib import Path
from typing import Any, Final

import pytest

from core import paths as core_paths
from core.registry import ProjectRegistry

#: Needed for `test_hermetic_registry_guard.py`, which runs a deliberately
#: unsandboxed nested test to prove the guard below actually fires.
pytest_plugins = ["pytester"]

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Where this process would read/write the registry with *no* test override in
#: effect — computed once, from the untouched environment, before any fixture
#: below has a chance to monkeypatch anything. Never opened: DG-460 forbids
#: this suite from reading the operator's real registry content, so only the
#: path it would resolve to is known, and only because `core.paths` is asked
#: for it the same way the runtime itself would.
_REAL_REGISTRY_PATH: Final = core_paths.registry_path().path.expanduser().resolve()


def _resolves_to_the_real_registry(registry_path: str | Path) -> bool:
    """True when *registry_path* is the operator's actual registry location.

    Compares paths only; never opens the file at either end.
    """
    resolved = Path(registry_path).expanduser().resolve()
    return bool(resolved == _REAL_REGISTRY_PATH)


#: Everything this repository puts on the import path under a generic name.
#: `core`, `scripts`, `route` and `service` are common enough that another
#: project's editable install claims them without anyone noticing.
OWN_PACKAGES = ("core", "scripts", "route", "jira_mcp")


def pytest_sessionstart(session: pytest.Session) -> None:
    """Fail the run if these tests would exercise somebody else's checkout.

    DG-268. `.venv` carried no pytest, so `uv run pytest` fell through to a
    pyenv shim -- a different interpreter -- whose site-packages held two
    editable installs left over from before the merge: `drunken_agy 1.1.0`,
    whose `.pth` put `~/Projects/drunken-team/src` on `sys.path`
    unconditionally, and `drunken_team 1.6.0`, mapping six of the names above
    to that same checkout.

    Every local run therefore imported the *fallback repository* rather than
    this one. It passed. Coverage read 0% across `src/` for exactly that
    reason and was filed as a reporting quirk for two rounds of review.

    Nothing else would have caught it: a suite testing the wrong code is green,
    and CI could not reproduce it, having one interpreter and one install.

    The remedy is `uv sync --extra dev`. Checked at session start rather than as
    a test, because the answer must arrive *before* seven hundred misleading
    passes, not among them.
    """
    stray = []
    for name in OWN_PACKAGES:
        try:
            module = importlib.import_module(name)
        except ImportError:  # not every package is importable in every context
            continue
        location = getattr(module, "__file__", None)
        if location is None:
            continue
        resolved = Path(location).resolve()
        if REPO_ROOT not in resolved.parents:
            stray.append(f"  {name:12} -> {resolved}")

    if not stray:
        return

    raise pytest.UsageError(
        "These tests would run another checkout's code, not this one:\n"
        + "\n".join(stray)
        + f"\n\nExpected everything under {REPO_ROOT}."
        + "\n\nUsually this means .venv has no pytest, so `uv run pytest` fell"
        + f" through to another interpreter ({sys.executable})."
        + "\n  Fix:  uv sync --extra dev"
        + "\n\nIf that is not it, look for a stale editable install claiming"
        + " these names:"
        + "\n  ls $(python -c 'import site; print(site.getsitepackages()[0])')"
        + "/__editable__*"
    )


def _jira_is_configured() -> bool:
    """True when there is enough config for a live Jira call to be meaningful.

    Uses the same loader the client uses, so this agrees with what the tests
    would actually get rather than second-guessing it.
    """
    try:
        from jira_mcp.config import get_jira_config

        config = get_jira_config()
    except Exception:  # noqa: BLE001 - absence of config must not error here
        return False
    return bool(config.get("jira_token") and config.get("jira_email"))


def pytest_collection_modifyitems(config: pytest.Config, items: list[Any]) -> None:
    """Skip live tests when there is nothing to talk to."""
    if _jira_is_configured():
        return

    skip = pytest.mark.skip(
        reason=(
            "No Jira credentials configured, so this end-to-end test has "
            "nothing to talk to. It creates real tickets when it does run — "
            "invoke it deliberately with `pytest -m e2e`."
        )
    )
    for item in items:
        if "e2e" in item.keywords:
            item.add_marker(skip)


@pytest.fixture(autouse=True)  # type: ignore[misc]
def hermetic_drunken_home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Every test gets its own, empty `$DRUNKEN_HOME` by default.

    DG-460: a test built as `doctor.run_doctor(offline=True)` or
    `ProjectRegistry()` with no override reads `core.paths.registry_path()`,
    which — absent a `DRUNKEN_HOME`/`DRUNKEN_REGISTRY_PATH` of its own — falls
    through to the operator's real `~/.drunken/projects.json`. That makes a
    result depend on whichever projects happen to be registered on the machine
    running the suite, and risks a registered project id reaching test output.

    This replaces "nothing set" with "a private, disposable directory" for
    every test, so a test that never thought about the registry still gets a
    harmless one. A test that needs specific *contents* still builds its own
    registry explicitly (see the `registry` fixtures already in this suite);
    this only changes what an override-free call sees.

    Runs before any test-module-local autouse fixture that also sets these
    (conftest autouse fixtures resolve first), so a file with its own, more
    specific override simply replaces this one — harmlessly.
    """
    sandbox_home = tmp_path / "dg460-drunken-home"
    monkeypatch.setenv(core_paths.ENV_HOME, str(sandbox_home))
    monkeypatch.delenv(core_paths.ENV_REGISTRY, raising=False)
    monkeypatch.delenv(core_paths.ENV_AUTH_DB, raising=False)


@pytest.fixture(autouse=True)  # type: ignore[misc]
def forbid_real_registry_access(monkeypatch: pytest.MonkeyPatch) -> None:
    """Fail, naming the test, if anything still reaches the real registry.

    Defense in depth for `hermetic_drunken_home` above: that fixture is what
    makes the suite hermetic; this is what stops the pattern from coming back
    if a future test unsets the override, or sets it back to nothing. Checked
    at `ProjectRegistry` construction — the one point every consumer
    (`doctor.run_doctor`, the CLI, the MCP server) funnels through before it
    can read or write anything — so the comparison runs before any file is
    opened, not after.
    """
    real_init = ProjectRegistry.__init__

    def guarded_init(self: ProjectRegistry, registry_path: str | None = None) -> None:
        real_init(self, registry_path)
        if _resolves_to_the_real_registry(self.registry_path):
            pytest.fail(
                "This test built a ProjectRegistry pointing at the operator's "
                f"real registry ({self.registry_path}). Tests must never read "
                "or write it (DG-460) — pass an explicit registry pointed at "
                "tmp_path, or set DRUNKEN_HOME/DRUNKEN_REGISTRY_PATH to one.",
                pytrace=False,
            )

    monkeypatch.setattr(ProjectRegistry, "__init__", guarded_init)
