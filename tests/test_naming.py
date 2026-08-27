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
import subprocess
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

        # DG-313: the label now carries the project, so one machine can run a
        # daemon per project. The base is what the two earlier names migrate
        # from, and install must know both or an already-installed agent is
        # orphaned rather than replaced -- it has KeepAlive, so an orphan keeps
        # a stale daemon alive on the shared socket.
        assert module._LABEL_BASE == "com.drunkenteam.daemon"
        assert module.LABEL.startswith(module._LABEL_BASE + ".")
        assert module.LABEL != module._LABEL_BASE

        assert "agy" in module.LEGACY_LABEL, (
            "The migration needs to know what it is migrating from, or an "
            "already-installed service is orphaned rather than replaced."
        )
        assert module.UNSUFFIXED_LABEL == "com.drunkenteam.daemon"
        assert callable(module._remove_unsuffixed_agent), (
            "Changing the label without unloading the un-suffixed agent leaves "
            "two loaded, and KeepAlive resurrects the old one."
        )


# ---------------------------------------------------------------------------
# DG-274 — the rest of the old identity
# ---------------------------------------------------------------------------

#: The board was renamed from `DT` to `DG` and the issues kept their numbers, so
#: every `DT-nnn` left in the tree is a key that finds nothing when searched. 61
#: files carried one, including the ticket-writing rules themselves.
OLD_TICKET_PREFIX = re.compile(r"\bDT-\d")

#: The product. `Drunken Team Inn`, `Drunken-Team`, `drunken-ai-team` and
#: `Drunken-Agy` are all names this project has stopped going by.
OLD_PRODUCT = re.compile(r"Drunken[- ]Team|drunken-ai-team|Drunken-Agy|drunken_agy\b")

#: Lines allowed to keep `drunken-team` in lower case, because each names a real
#: thing that still exists rather than describing this project:
#:
#:   * `~/Projects/drunken-team` — the fallback checkout, under standing
#:     instruction not to be touched. Naming it is the instruction.
#:   * `uv tool uninstall drunken-team` — the remedy a reader has to run.
#:   * `uv/tools/drunken-team` — the legacy tool root doctor looks for.
#:   * the accounts of DG-266 and DG-268, which cannot describe the bug without
#:     naming what the code used to say.
#:   * the registry's own project list. `drunken-team` is a live key in
#:     `~/.drunken/projects.json`, pointing at the fallback checkout this repo is
#:     under standing instruction to keep. Reporting what the registry holds has
#:     to report that key.
#:   * DG-306's fixture and finding, which needs a second live registry key
#:     distinct from `drunken-guild` to demonstrate the multi-project bug --
#:     `drunken-team` is the real one that actually exposed it.
LOWERCASE_ALLOWED = (
    "~/Projects/drunken-team",
    "uv tool uninstall drunken-team",
    "uv/tools/drunken-team",
    "drunken-team v2.1.0",
    "drunken_team 1.6.0",
    "drunken_agy 1.1.0",
    'tmp_path / "drunken-team"',
    "still owns those names",
    "from `drunken-team` to `drunken-guild`",
    "naming ``drunken-team``",
    "`drunken-team`, the fallback",
    "drunken-team/src",
    "`drunken-guild`, `drunken-team`, `isac`, `twa`",
    "drunken-team registered before drunken-guild",
    "resolved to drunken-team's channel",
    '"drunken-team": {',
)

#: Records exist to name what was retired, so they are exempt wholesale.
RECORD_PREFIXES = ("_not_used/",)

#: The two files that cannot do their job without writing the old names down.
#: This one holds the patterns; `check_doc_drift.py` holds the list of retired
#: strings it greps documentation for. A guard that forbade its own subject
#: would be a guard nobody could write.
SELF_EXEMPT = frozenset({"tests/test_naming.py", "scripts/check_doc_drift.py"})


def _tracked_files() -> list[str]:
    out = subprocess.run(
        ["git", "ls-files"], cwd=REPO_ROOT, capture_output=True, text=True, check=False
    )
    return [
        f
        for f in out.stdout.split()
        if not f.startswith(RECORD_PREFIXES) and f not in SELF_EXEMPT
    ]


def _offenders(pattern: re.Pattern) -> list[str]:
    hits = []
    for relative in _tracked_files():
        path = REPO_ROOT / relative
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        for n, line in enumerate(text.splitlines(), 1):
            if pattern.search(line) and not any(k in line for k in LOWERCASE_ALLOWED):
                hits.append(f"{relative}:{n}: {line.strip()[:100]}")
    return hits


class TestTheOldIdentityIsGone:
    """DG-274. The rename stopped at the package name and left the rest.

    A sweep has a shelf life; a test does not. Each of these was a real finding,
    not a hypothetical: 61 files citing dead ticket keys, five templates that
    other projects copy naming the old product, two install scripts telling a
    user to check they were in a repository that no longer exists.
    """

    def test_no_dead_ticket_keys(self) -> None:
        hits = _offenders(OLD_TICKET_PREFIX)
        assert not hits, (
            "The board is DG and these keys find nothing when searched:\n  "
            + "\n  ".join(hits)
        )

    def test_no_old_product_name(self) -> None:
        hits = _offenders(OLD_PRODUCT)
        assert not hits, "The product is drunken-guild:\n  " + "\n  ".join(hits)

    def test_lowercase_survivors_are_all_deliberate(self) -> None:
        """`drunken-team` in lower case is allowed only where it names something
        that really exists — the fallback checkout, the uninstall remedy, the
        legacy tool root, or the account of a bug that cannot be told without
        it. Anything else is a leftover."""
        hits = _offenders(re.compile(r"drunken[-_]team"))
        assert not hits, (
            "Add to LOWERCASE_ALLOWED with the reason, or use the new name:\n  "
            + "\n  ".join(hits)
        )
