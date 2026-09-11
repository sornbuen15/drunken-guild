"""The `.env` parent-walk must not come back — DG-275.

This file used to assert that `load_dotenv()` ran without crashing. The walk it
was guarding is the vulnerability: it climbed from `os.getcwd()` through every
parent, loaded the first `.env` it found into `os.environ`, and ran at import.

Config precedence puts an environment variable first *because* an env var is
explicit and named. A `.env` picked up by climbing arrived disguised as rule 1
and outranked the registry. DG-254 removed exactly this from the daemon; it
survived in the two scripts the daemon spawns, and `discord_router` spawns
`jira_bridge.py` for `/tasks`, `/pr`, `/next` and `/refine`.

So the test is inverted: it now fails if the walk returns.
"""

import re
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent

#: The Confluence bridge was retired with confluence-sync (DG-352).
BRIDGES = ("scripts/jira_bridge.py",)

#: `os.getcwd()` and a loop over `os.path.dirname` is the signature CLAUDE.md
#: names. `dirname(abspath(__file__))` is not it — locating *packaged code*
#: relative to the source is required, and only *state* may never be.
WALK = re.compile(r"os\.getcwd\(\)")
DOTENV = re.compile(r"load_dotenv|_load_env_file|\.env['\"]")


@pytest.mark.parametrize("relative", BRIDGES)  # type: ignore[misc]
def test_a_bridge_does_not_read_a_dotenv(relative: str) -> None:
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    body = "\n".join(
        line for line in text.splitlines() if not line.lstrip().startswith("#")
    )
    hits = [line.strip()[:90] for line in body.splitlines() if DOTENV.search(line)]
    assert not hits, (
        f"{relative} reads a .env again. An environment variable is rule 1 "
        "because it is explicit and named; a file found by climbing is neither "
        "and must not become one:\n  " + "\n  ".join(hits)
    )


@pytest.mark.parametrize("relative", BRIDGES)  # type: ignore[misc]
def test_a_bridge_does_not_resolve_credentials_from_the_current_directory(
    relative: str,
) -> None:
    """`os.getcwd()` decides where a *command* runs, never who we authenticate
    as. The daemon is launched by launchd from a directory nobody chose."""
    text = (REPO_ROOT / relative).read_text(encoding="utf-8")
    lines = [
        line.strip()[:90]
        for line in text.splitlines()
        if WALK.search(line) and not line.lstrip().startswith("#")
    ]
    credentialish = [
        line
        for line in lines
        if re.search(r"token|secret|credential|\.env", line, re.I)
    ]
    assert not credentialish, (
        f"{relative} resolves a credential from the working directory:\n  "
        + "\n  ".join(credentialish)
    )
