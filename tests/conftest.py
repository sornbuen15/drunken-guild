"""Shared pytest configuration.

The `e2e` tests talk to the real Jira instance and **create real tickets**. The
marker was added with the comment "so it doesn't run on standard unit test runs
unless requested" — but nothing ever acted on it, so every plain `pytest` run
filed two more tickets into the live DT project. DT-169 through DT-223 are the
accumulated result.

Two things stop that now. `pyproject.toml`'s addopts deselects `e2e` by default,
which is what the marker always meant. And the hook below skips those tests when
credentials are absent rather than letting them fail with a bare
"Missing credentials" -- which is what CI hit, since CI has no `.env`.

Run them deliberately, against a project you are willing to write to:

    pytest -m e2e
"""

from __future__ import annotations

from typing import Any

import pytest


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
