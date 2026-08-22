# mypy: ignore-errors
"""The product is drunken-guild. Nothing we own should still say "agy".

The catch is that the same three letters mean two different things here, and
only one of them is ours:

* ``agy`` the **command** is Antigravity's CLI, at ``/opt/homebrew/bin/agy``.
  The router builds ``["agy", ...]`` to dispatch work to it and the runner
  gates on it. The ``agy_response`` key is what that CLI answers with.
  Both are an external contract; renaming either breaks agent dispatch.
* Everything else — a pid file, a log name, a launchd label, an env var — is
  ours, and carries a name the product no longer goes by.

So this file asserts the rename in one direction and pins the contract in the
other, because a later sweep with no test would take both.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: Ours. Nothing here may mention the old name.
OWNED = (
    "src/core/paths.py",
    "src/service/discord_listener.py",
    "src/service/approval_manager.py",
    "scripts/check_pending_approval.py",
)

#: `scripts/setup_daemon_service.py` is exempt for one reason: it has to still
#: know the old launchd label in order to unload and delete it. Forgetting the
#: name is what would leave the previous agent installed forever. It is covered
#: by TestTheServiceLabelMigrates instead.

#: Where the external contract lives, and is expected to stay.
ANTIGRAVITY_BOUNDARY = (
    "src/service/discord_router.py",
    "src/service/discord_runner.py",
)

#: `agy` as a whole word, so `antigravity` and prose about Antigravity do not
#: trip it.
AGY = re.compile(r"\bagy\b|\bAGY\b|agy_pids|agy_discord|agy-daemon|_agy_")


@pytest.mark.parametrize("relative", OWNED)  # type: ignore[misc]
def test_our_own_artefacts_no_longer_carry_the_old_name(relative: str) -> None:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    hits = [
        f"{n}: {line.strip()}"
        for n, line in enumerate(text.splitlines(), 1)
        if AGY.search(line)
    ]
    assert not hits, f"{relative} still names 'agy':\n  " + "\n  ".join(hits)


class TestTheAntigravityContractIsPinned:
    """These are deliberately *not* renamed. A test that only deleted the name
    everywhere would take the dispatch integration with it, silently — the
    failure would be an agent that never runs, with no error to read."""

    def test_the_dispatch_command_is_still_agy(self) -> None:
        text = (REPO_ROOT / "src/service/discord_router.py").read_text(encoding="utf-8")
        assert '"agy",' in text, (
            "The router no longer invokes the 'agy' CLI. That is Antigravity's "
            "binary name, not ours, and dispatch cannot work without it."
        )

    def test_the_response_key_is_still_agy_response(self) -> None:
        text = (REPO_ROOT / "src/service/discord_router.py").read_text(encoding="utf-8")
        assert "agy_response" in text, (
            "'agy_response' is the key the Antigravity CLI answers with. "
            "Renaming it here just stops us reading its output."
        )

    def test_the_runner_still_recognises_the_agy_command(self) -> None:
        text = (REPO_ROOT / "src/service/discord_runner.py").read_text(encoding="utf-8")
        assert '"agy"' in text


class TestTheServiceLabelMigrates:
    """Changing the launchd label without removing the old plist leaves two
    definitions registered, and the old one keeps restarting a stale daemon
    under KeepAlive."""

    def test_install_knows_the_previous_label(self) -> None:
        import importlib.util

        spec = importlib.util.spec_from_file_location(
            "setup_daemon_service",
            REPO_ROOT / "scripts" / "setup_daemon_service.py",
        )
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)

        assert module.LABEL == "com.drunkenteam.daemon"
        assert "agy" in module.LEGACY_LABEL, (
            "The migration needs to know what it is migrating from, or an "
            "already-installed service is orphaned rather than replaced."
        )
